from app.orchestration.state import (
    EnvironmentState,
    Room,
    Mode,
    DoorState,
    PowerState,
    PreparationState,
)


class ContextManager:

    def __init__(self):
        self.state = EnvironmentState()

    def get_state(self) -> EnvironmentState:
        return self.state

    def get_current_room(self) -> Room:
        return self.state.current_room

    def get_return_target(self):
        return self.state.return_target

    def get_current_mode(self) -> Mode:
        return self.state.current_mode

    def set_current_room(self, room: Room):
        self.state.current_room = room

    def set_return_target(self, room):
        self.state.return_target = room

    def clear_return_target(self):
        self.state.return_target = None

    def set_mode(self, mode: Mode):
        self.state.current_mode = mode

    def set_drawing_light(self, state: PowerState):
        self.state.drawing_light = state

    def set_exit_door(self, state: DoorState):
        self.state.exit_door = state

    def set_buzzer(self, state: PowerState):
        self.state.buzzer = state

    def set_device_state(
        self,
        room: Room,
        device: str,
        value
    ):
        if room == Room.STUDY_ROOM:
            setattr(self.state.study, device, value)

        elif room == Room.RELAX_ROOM:
            setattr(self.state.relax, device, value)

        elif room == Room.SLEEP_ROOM:
            setattr(self.state.sleep, device, value)

        elif room == Room.MEAL_ROOM:
            setattr(self.state.meal, device, value)

    def print_state(self):
        print("\n" + "=" * 60)
        print("ENVIRONMENT STATE")
        print("=" * 60)

        print(f"Current Room : {self.state.current_room.value}")
        return_target = (
            self.state.return_target.value
            if self.state.return_target
            else "NONE"
        )

        print(f"Return Target: {return_target}")
        print(f"Current Mode : {self.state.current_mode.value}")

        print(
            f"Drawing Light: "
            f"{self.state.drawing_light.value}"
        )

        print(
            f"Exit Door: "
            f"{self.state.exit_door.value}"
        )

        print(
            f"Buzzer: "
            f"{self.state.buzzer.value}"
        )

        print("\nStudy:")
        print(f"  Door : {self.state.study.door.value}")
        print(f"  Light: {self.state.study.light.value}")
        print(f"  Table: {self.state.study.table.value}")

        print("\nRelax:")
        print(f"  Door : {self.state.relax.door.value}")
        print(f"  Light: {self.state.relax.light.value}")
        print(f"  TV   : {self.state.relax.tv.value}")

        print("\nSleep:")
        print(f"  Door : {self.state.sleep.door.value}")
        print(f"  Light: {self.state.sleep.light.value}")
        print(f"  Bed  : {self.state.sleep.bed.value}")
        print(
            f"  Medication: "
            f"{self.state.sleep.medication_servo.value}"
        )

        print("\nMeal:")
        print(f"  Door : {self.state.meal.door.value}")
        print(f"  Light: {self.state.meal.light.value}")
        print(f"  Table: {self.state.meal.table.value}")

        print("=" * 60)