from typing import List, Dict, Union


class Exercise:
    def __init__(self, exercise_id: int, reps: int, sets: int, weights: str, rest: str):
        self.exercise_id = exercise_id
        self.reps = reps
        self.sets = sets
        self.weights = weights
        self.rest = rest


class Running:
    def __init__(self, type: str, distance: str, pace: str, rest: str):
        self.type = type
        self.distance = distance
        self.pace = pace
        self.rest = rest


class Daily:
    def __init__(
        self,
        date: str,
        theme: str,
        exercises: List[Exercise],
        running: Union[Running, None] = None,
        hyrox_specific: str = None,
    ):
        self.date = date
        self.theme = theme
        self.exercises = exercises
        self.running = running
        self.hyrox_specific = hyrox_specific


class Plan:
    def __init__(self, date: str, workouts: List[Daily], reasoning: str):
        self.date = date
        self.workouts = workouts
        self.reasoning = reasoning


# Create realistic sample data
exercise1 = Exercise(exercise_id=1, reps=10, sets=3, weights="20 lbs", rest="1 min")
exercise2 = Exercise(exercise_id=2, reps=15, sets=4, weights="15 lbs", rest="1.5 min")
running1 = Running(type="Interval", distance="5 km", pace="5 min/km", rest="2 min")

daily1 = Daily(date="2022-01-01", exercises=[exercise1, exercise2])
daily2 = Daily(date="2022-01-02", exercises=[exercise1], running=None)
daily3 = Daily(date="2022-01-03", exercises=[], running=running1)

plan = Plan(
    date="2022-01-01",
    workouts=[daily1, daily2, daily3],
    reasoning="Reason for choosing the exercises.",
)


# Define a method to pretty print the plan
def pretty_print_plan(plan):
    print("Plan:")
    print(f"Date: {plan.date}")
    print(f"Reasoning: {plan.reasoning}")
    print("\nWorkouts:")
    for workout in plan.workouts:
        print(f"  Date: {workout.date}")
        print(f"  Exercises:")
        for exercise in workout.exercises:
            print(f"    Exercise ID: {exercise.exercise_id}")
            print(f"    Reps: {exercise.reps}")
            print(f"    Sets: {exercise.sets}")
            print(f"    Weights: {exercise.weights}")
            print(f"    Rest: {exercise.rest}")
        if workout.running:
            print(f"  Running:")
            print(f"    Type: {workout.running.type}")
            print(f"    Distance: {workout.running.distance}")
            print(f"    Pace: {workout.running.pace}")
            print(f"    Rest: {workout.running.rest}")
        print("\n")


# Call the pretty print function
pretty_print_plan(plan)
