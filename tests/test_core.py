import unittest

from core.learn import learn_program
from core.passport import create_passport, verify_passport
from core.robot import plan_execution, verify_execution

BINS = [
    {"id": "bin-red", "color": "red", "x": 40, "y": 28, "w": 150, "h": 86},
    {"id": "bin-blue", "color": "blue", "x": 245, "y": 28, "w": 150, "h": 86},
    {"id": "bin-yellow", "color": "yellow", "x": 450, "y": 28, "w": 150, "h": 86},
]
TRACKS = [
    {"object_id": "cube-red", "color": "red", "start": {"x": 124, "y": 336}, "end": {"x": 115, "y": 71}},
    {"object_id": "cube-blue", "color": "blue", "start": {"x": 309, "y": 336}, "end": {"x": 320, "y": 71}},
    {"object_id": "cube-yellow", "color": "yellow", "start": {"x": 494, "y": 336}, "end": {"x": 525, "y": 71}},
]


class LearnTests(unittest.TestCase):
    def test_learns_sort_by_color(self):
        p = learn_program(TRACKS, BINS)
        self.assertEqual(p["task"], "sort_by_color")
        self.assertTrue(p["generalizes"])
        self.assertEqual(p["rules"]["red"], "bin-red")
        self.assertEqual(p["confidence"], 1.0)

    def test_unexplained_track(self):
        bad = [{"object_id": "cube-red", "color": "red",
                "start": {"x": 0, "y": 0}, "end": {"x": 620, "y": 400}}]
        p = learn_program(bad, BINS)
        self.assertEqual(p["unexplained"], ["cube-red"])

    def test_plan_and_verify_shuffled(self):
        p = learn_program(TRACKS, BINS)
        shuffled = [
            {"id": "cube-red", "color": "red", "x": 540, "y": 330},
            {"id": "cube-blue", "color": "blue", "x": 90, "y": 340},
            {"id": "cube-yellow", "color": "yellow", "x": 320, "y": 325},
        ]
        plan = plan_execution(shuffled, BINS, p)
        self.assertEqual(plan["count"], 3)
        final = [{"id": a["object"], "color": a["color"], "x": a["to"]["x"], "y": a["to"]["y"]}
                 for a in plan["actions"]]
        v = verify_execution(final, BINS)
        self.assertEqual(v["score"], 100)

    def test_verify_detects_wrong_bin(self):
        wrong = [{"id": "cube-red", "color": "red", "x": 320, "y": 71}]  # in blue bin
        self.assertEqual(verify_execution(wrong, BINS)["score"], 0)


class PassportTests(unittest.TestCase):
    def test_passport_round_trip_and_tamper(self):
        p = learn_program(TRACKS, BINS)
        passport = create_passport(p, {"score": 100})
        self.assertTrue(verify_passport(passport)["valid"])
        passport["program"]["rules"]["red"] = "bin-blue"  # tamper
        self.assertFalse(verify_passport(passport)["valid"])


if __name__ == "__main__":
    unittest.main()
