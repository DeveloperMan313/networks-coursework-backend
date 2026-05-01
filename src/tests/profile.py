import cProfile
import unittest

from src.tests.test_application import TestPC_app, TestPort_app
from src.tests.test_channel import TestPort_cha
from src.tests.test_physical import TestPort_phy

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPort_phy))
    suite.addTests(loader.loadTestsFromTestCase(TestPort_cha))
    suite.addTests(loader.loadTestsFromTestCase(TestPort_app))
    suite.addTests(loader.loadTestsFromTestCase(TestPC_app))

    profiler = cProfile.Profile()
    profiler.enable()
    unittest.TextTestRunner().run(suite)
    profiler.disable()

    profiler.dump_stats("tests.prof")
    print("Profile data saved to tests.prof")
