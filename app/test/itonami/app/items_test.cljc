(ns itonami.app.items-test
  (:require [clojure.test :refer [deftest is testing]]
            [itonami.app.items :as items]))

(def file
  {"schema" "itonami.items.v1"
   "items" [{"id" "IT-1" "title" "Add worktrees view" "status" "In progress" "assignee" "junkawasaki"}
            {"id" "IT-2" "title" "Add items view" "status" "Waiting"}
            {"id" "IT-3" "title" "Approve merge" "status" "Needs you"
             "ask" {"question" "Approve the PR?" "options" [{"id" "yes" "label" "Approve"} {"label" "Hold"}]}}
            {"id" "IT-4" "title" "Ship docs" "status" "Done"}
            {"id" "IT-5" "title" "Odd status" "status" "Banana"}
            {"title" "No id" "status" "Waiting"}
            {"id" "IT-6" "title" "Broken ask" "status" "Needs you" "ask" {"question" "" "options" [{"label" "X"}]}}]})

(def parsed (items/items-from file))

(deftest file-parsing
  (is (= :items (items/kind-of file)))
  (is (nil? (items/kind-of {"schema" "other" "items" []})))
  (is (:error (items/items-from {"schema" "other" "items" []})))
  (is (= 2 (:dropped parsed)))
  (is (= 5 (count (:items parsed))))
  (testing "unknown status and missing id are dropped, not guessed"
    (is (not (some #(= "IT-5" (:id %)) (:items parsed))))
    (is (not (some #(= "No id" (:title %)) (:items parsed))))))

(deftest statuses-and-ask
  (is (= [:in-progress :waiting :needs-you :done :needs-you]
         (map :status (sort-by #(:id %) (:items parsed)))))
  (let [by-id (into {} (map (juxt :id identity) (:items parsed)))]
    (testing "Needs-you shows the question and the option labels, display-only"
      (is (= "Approve the PR?" (get-in by-id ["IT-3" :ask :question])))
      (is (= ["Approve" "Hold"] (map :label (get-in by-id ["IT-3" :ask :options]))))
      (is (= ["yes" "1"] (map :id (get-in by-id ["IT-3" :ask :options])))))
    (testing "a blank ask question is not shown"
      (is (nil? (:ask (by-id "IT-6"))))
      (is (= :needs-you (:status (by-id "IT-6"))))))
  (is (= {:total 5 :in-progress 1 :waiting 1 :needs-you 2 :done 1}
         (items/summary (:items parsed)))))

(deftest filter-by
  (is (= 5 (count (items/filter-by (:items parsed) :all ""))))
  (is (= ["IT-3" "IT-6"] (map :id (items/filter-by (:items parsed) :needs-you ""))))
  (is (= ["IT-1"] (map :id (items/filter-by (:items parsed) :all "junkawasaki"))))
  (is (= ["IT-4"] (map :id (items/filter-by (:items parsed) :done "ship"))))
  (is (empty? (items/filter-by (:items parsed) :waiting "approve"))))
