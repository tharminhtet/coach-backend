from typing import List, Dict
from datetime import date


class UserStats:
    def __init__(
        self,
        date_measured: date,
        available_equipments: List[str],
        fitness_stats: Dict[str, str],
        body_measurements: Dict[str, str],
        goals: List[Dict[str, str]],
        constraints: List[str],
    ):
        self.date_measured = date_measured.strftime("%Y%m%d")
        self.available_equipments = available_equipments
        self.fitness_stats = fitness_stats
        self.body_measurements = body_measurements
        self.goals = goals
        self.constraints = constraints

    def update_goals(self, new_goals: List[Dict[str, str]]):
        self.goals = new_goals

    def add_constraint(self, constraint: str):
        self.constraints.append(constraint)

    def remove_constraint(self, constraint: str):
        self.constraints = [c for c in self.constraints if c != constraint]

    def update_fitness_stat(self, stat_name: str, new_value: str):
        self.fitness_stats[stat_name] = new_value

    def update_body_measurement(self, measurement_name: str, new_value: str):
        self.body_measurements[measurement_name] = new_value


class UserProfile:
    def __init__(self, user_id: str, name: str, age: int, gender: str):
        self.user_id = user_id
        self.name = name
        self.age = age
        self.gender = gender
        self.stats: List[UserStats] = []

    def add_stats(
        self,
        date_measured: date,
        available_equipments: List[str],
        fitness_stats: Dict[str, str],
        body_measurements: Dict[str, str],
        goals: List[Dict[str, str]],
        constraints: List[str],
    ):
        new_stats = UserStats(
            date_measured,
            available_equipments,
            fitness_stats,
            body_measurements,
            goals,
            constraints,
        )
        self.stats.append(new_stats)

    def get_latest_stats(self) -> UserStats:
        return self.stats[-1] if self.stats else None

    def update_goals(self, new_goals: List[Dict[str, str]]):
        if self.stats:
            self.stats[-1].update_goals(new_goals)

    def add_constraint(self, constraint: str):
        if self.stats:
            self.stats[-1].add_constraint(constraint)

    def remove_constraint(self, constraint: str):
        if self.stats:
            self.stats[-1].remove_constraint(constraint)

    def update_fitness_stat(self, stat_name: str, new_value: str):
        if self.stats:
            self.stats[-1].update_fitness_stat(stat_name, new_value)

    def update_body_measurement(self, measurement_name: str, new_value: str):
        if self.stats:
            self.stats[-1].update_body_measurement(measurement_name, new_value)
