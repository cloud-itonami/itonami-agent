(ns itonami.app.worktrees-test
  (:require [clojure.test :refer [deftest is testing]]
            [itonami.app.worktrees :as w]))

(def snapshot
  {"schema" "itonami.worktrees-snapshot.v1"
   "observedAt" "2026-11-25T00:00:00Z"
   "worktrees" [{"path" "/repos/itonami-agent" "branch" "refs/heads/main" "head" "abc1234" "main" true}
                {"path" "/repos/itonami-agent-wt/feature" "branch" "refs/heads/feature-x" "head" "def5678"}
                {"path" "/repos/bare.git" "bare" true}
                {"path" "/repos/prunable" "head" "9999999" "prunable" true}
                {"path" "/repos/locked" "branch" "refs/heads/lock" "locked" true}
                {"path" "   " "branch" "refs/heads/ghost"}
                {"no-path" true}]})

(def parsed (w/worktrees-from snapshot))

(deftest snapshot-parsing
  (is (= :worktrees (w/kind-of snapshot)))
  (is (nil? (w/kind-of {"schema" "other"})))
  (is (:error (w/worktrees-from {"schema" "other" "worktrees" []})))
  (is (= "2026-11-25T00:00:00Z" (:observed-at parsed)))
  (is (= 2 (:dropped parsed)))
  (is (= 5 (count (:worktrees parsed))))
  (testing "main sorts first, branch is stripped of refs/heads/, bare wins"
    (is (= "/repos/itonami-agent" (:path (first (:worktrees parsed)))))
    (is (= "main" (:branch (first (:worktrees parsed)))))
    (is (= :bare (w/wt-status (nth (:worktrees parsed) 1))))
    (is (= "feature-x" (:branch (nth (:worktrees parsed) 2))))
    (is (= :worktree (w/wt-status (nth (:worktrees parsed) 2))))
    (is (= :locked (w/wt-status (nth (:worktrees parsed) 3))))
    (is (= :prunable (w/wt-status (nth (:worktrees parsed) 4))))))

(deftest summary-and-filter
  (is (= {:total 5 :main 1 :linked 1 :bare 1 :locked 1 :prunable 1}
         (w/summary (:worktrees parsed))))
  (is (= 5 (count (w/filter-by (:worktrees parsed) ""))))
  (is (= 1 (count (w/filter-by (:worktrees parsed) "feature"))))
  (is (= 1 (count (w/filter-by (:worktrees parsed) "LOCKED"))))
  (testing "a blank path is not a worktree; a snapshot is a reading, not a claim"
    (is (empty? (w/filter-by (:worktrees parsed) "ghost")))))
