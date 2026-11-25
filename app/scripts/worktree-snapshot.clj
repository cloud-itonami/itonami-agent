;; Build an itonami.worktrees-snapshot.v1 file for the Itonami app's
;; Worktrees view from `git worktree list --porcelain`.
;;
;;   bb scripts/worktree-snapshot.clj OUT.json REPO...
;;
;; Reads only; writes OUT.json. The output holds repository paths, branch
;; names and HEAD ids only — no file contents, no secrets.
(require '[cheshire.core :as json]
         '[clojure.java.shell :as sh]
         '[clojure.string :as str])

(defn parse-porcelain
  "Parse `git worktree list --porcelain` into rows. Each block is one worktree:
  `worktree <path>`, `HEAD <sha>`, `branch <ref>`, and optional `bare`,
  `detached`, `locked`, `prunable` lines."
  [text]
  (for [block (str/split text #"\n\n")
        :let [lines (keep (fn [line] (when-not (str/blank? line) line))
                          (str/split-lines block))
              m (into {} (for [line lines
                               :let [[k v] (str/split line #" " 2)]]
                           [k (or v true)]))]
        :when (get m "worktree")]
    {"path" (get m "worktree")
     "head" (get m "HEAD")
     "branch" (get m "branch")
     "bare" (boolean (get m "bare"))
     "detached" (boolean (get m "detached"))
     "locked" (boolean (get m "locked"))
     "prunable" (boolean (get m "prunable"))}))

(defn mark-mains
  "Mark the first non-bare row of each repository's list as its main worktree."
  [groups]
  (vec (mapcat (fn [rows]
                 (loop [rows (seq rows), left true, acc []]
                   (if (nil? rows)
                     acc
                     (let [w (first rows)
                           mark (and left (not (get w "bare")))]
                       (recur (next rows) (if mark false left)
                              (conj acc (if mark (assoc w "main" true) w)))))))
               groups)))

(let [[out & roots] *command-line-args*]
  (when (or (nil? out) (empty? roots))
    (binding [*out* *err*] (println "usage: OUT.json REPO..."))
    (System/exit 64))
  (let [groups (for [root roots
                     :let [res (sh/sh "git" "-C" root "worktree" "list" "--porcelain")]
                     :when (zero? (:exit res))]
                 (parse-porcelain (:out res)))
        worktrees (mark-mains groups)
        snap {"schema" "itonami.worktrees-snapshot.v1"
              "observedAt" (str (java.time.Instant/now))
              "worktrees" worktrees}]
    (spit out (json/generate-string snap))
    (println (format "%d worktrees from %d repos, observed %s -> %s"
                     (count worktrees) (count roots) (get snap "observedAt") out))))
