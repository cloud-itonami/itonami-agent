(ns itonami.app.items
  "Work items (an Orca items equivalent), read from a file the person brings.

  The app never talks to Orca: its CSP allows only the local IPC and the Agent
  origin, and it has no shell or filesystem permission. Items are therefore
  imported as an `itonami.items.v1` JSON file in the same pattern as
  `itonami.app.autonomy`'s three-file import. A file can be produced from an
  Orca orchestration export or written by hand; the reader validates it and
  refuses anything else. Imported items live in memory only.

  Only reading: a Needs-you item shows its question and option labels, but
  answering it is a write and is not performed here. A status in the file is
  shown as given; refresh means importing a newer file.

  Pure."
  (:require [clojure.string :as str]))

(def schema "itonami.items.v1")

(def status-order [:in-progress :waiting :needs-you :done])

(def status-index (zipmap status-order (range)))

(def status-labels {:in-progress "In progress" :waiting "Waiting"
                    :needs-you "Needs you" :done "Done"})

(defn- as-str [v] (when (and (string? v) (not (str/blank? v))) v))

(defn- status-of [s]
  (when (string? s)
    (let [k (keyword (str/replace (str/lower-case (str/trim s)) #" " "-"))]
      (when (contains? status-index k) k))))

(defn kind-of
  "The file kind when v is an items file, else nil."
  [v]
  (when (and (map? v) (= schema (get v "schema")) (sequential? (get v "items")))
    :items))

(defn- ask-of [a]
  (when (and (map? a) (string? (get a "question")))
    (let [question (get a "question")
          opts (vec (keep (fn [o] (when (and (map? o) (string? (get o "label"))) o))
                              (get a "options")))
          indexed (map-indexed (fn [i o] (assoc o :idx i)) opts)
          opts (vec (for [o indexed]
                      {:id (or (as-str (get o "id")) (str (:idx o)))
                       :label (get o "label")}))]
      (when-not (str/blank? question)
        {:question question :options opts}))))

(defn- item-row [it]
  (when (map? it)
    (let [id (as-str (get it "id"))
          status (status-of (get it "status"))]
      (when (and id status)
        {:id id
         :title (or (as-str (get it "title")) id)
         :status status
         :assignee (as-str (get it "assignee"))
         :updated (as-str (get it "updated"))
         :summary (as-str (get it "summary"))
         :ask (ask-of (get it "ask"))}))))

(defn items-from
  "Normalize an `itonami.items.v1` value.
  {:error …} when it is not one. An item without an id or with an unknown
  status is skipped and counted in :dropped; a Needs-you item whose ask is
  malformed keeps its status but shows no question."
  [v]
  (if-not (kind-of v)
    {:error "not an itonami.items.v1 file"}
    (let [raw (get v "items")
          rows (vec (keep item-row raw))]
      {:items (vec (sort-by (fn [it] [(status-index (:status it))
                                      (str/lower-case (:title it))]) rows))
       :dropped (- (count raw) (count rows))})))

(defn summary
  "Count per status, over the normalized items."
  [items]
  (let [c (frequencies (map :status items))]
    {:total (count items)
     :in-progress (get c :in-progress 0)
     :waiting (get c :waiting 0)
     :needs-you (get c :needs-you 0)
     :done (get c :done 0)}))

(defn filter-by
  "Items matching a status (:all keeps every status) and a query over
  id, title and assignee; a blank query matches everything."
  [items status q]
  (cond->> items
    (not= :all status) (filterv #(= status (:status %)))
    (not (or (nil? q) (str/blank? q)))
    (filterv (fn [it]
               (let [needle (str/lower-case (str/trim q))]
                 (or (str/includes? (str/lower-case (:id it)) needle)
                     (str/includes? (str/lower-case (:title it)) needle)
                     (str/includes? (str/lower-case (or (:assignee it) "")) needle)))))))
