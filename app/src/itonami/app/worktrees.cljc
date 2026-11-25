(ns itonami.app.worktrees
  "Git worktrees as a list, from a snapshot the person brings to the app.

  The app never runs `git` itself (no shell permission, and the browser/Android
  surfaces cannot see the filesystem). `scripts/worktree-snapshot.clj` reads
  `git worktree list --porcelain` for one or more repositories and writes an
  `itonami.worktrees-snapshot.v1` JSON file; this namespace validates and
  normalizes that file, in the same pattern as `itonami.app.autonomy`.

  Pure. Status here is a reading of the snapshot, not a claim about the
  filesystem now: a worktree that has since moved stays listed until a new
  snapshot is imported."
  (:require [clojure.string :as str]))

(def schema "itonami.worktrees-snapshot.v1")

(defn- as-str [v] (when (and (string? v) (not (str/blank? v))) v))

(defn- strip-heads [branch]
  (cond
    (nil? branch) nil
    (str/starts-with? branch "refs/heads/") (subs branch (count "refs/heads/"))
    (str/starts-with? branch "refs/") branch
    :else branch))

(defn- worktree-row [w]
  (when (map? w)
    (let [path (as-str (get w "path"))]
      (when path
        {:path path
         :branch (strip-heads (as-str (get w "branch")))
         :head (as-str (get w "head"))
         :bare? (boolean (get w "bare"))
         :main? (boolean (get w "main"))
         :locked? (boolean (get w "locked"))
         :detached? (boolean (get w "detached"))
         :prunable? (boolean (get w "prunable"))}))))

(defn kind-of
  "The file kind when v is a worktrees snapshot, else nil."
  [v]
  (when (and (map? v) (= schema (get v "schema")) (sequential? (get v "worktrees")))
    :worktrees))

(defn worktrees-from
  "Normalize an `itonami.worktrees-snapshot.v1` value.
  {:error …} when it is not one; a worktree without a path is skipped."
  [v]
  (if-not (kind-of v)
    {:error "not an itonami.worktrees-snapshot.v1 file"}
    (let [rows (vec (keep worktree-row (get v "worktrees")))]
      {:observed-at (as-str (get v "observedAt"))
       :worktrees (vec (sort-by (fn [w] [(if (:main? w) 0 1) (:path w)]) rows))
       :dropped (- (count (get v "worktrees")) (count rows))})))

(defn wt-status
  "A worktree's display status. A bare repository wins over main/linked."
  [w]
  (cond (:bare? w) :bare
        (:prunable? w) :prunable
        (:locked? w) :locked
        (:main? w) :main
        :else :worktree))

(def status-labels {:main "Main" :worktree "Worktree" :bare "Bare"
                    :locked "Locked" :prunable "Prunable"})

(defn summary
  "Counts over the rows: total, main, linked, bare, locked."
  [rows]
  (let [c (frequencies (map wt-status rows))]
    {:total (count rows)
     :main (get c :main 0)
     :linked (get c :worktree 0)
     :bare (get c :bare 0)
     :locked (get c :locked 0)
     :prunable (get c :prunable 0)}))

(defn filter-by
  "Rows matching a query over path and branch; blank query keeps all rows."
  [rows q]
  (if (or (nil? q) (str/blank? q))
    rows
    (let [needle (str/lower-case (str/trim q))]
      (filterv (fn [w] (or (str/includes? (str/lower-case (:path w)) needle)
                           (str/includes? (str/lower-case (or (:branch w) "")) needle)))
               rows))))
