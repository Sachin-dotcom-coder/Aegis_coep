"""
 Prevents false alarms. A single bad frame shouldn't trigger an incident.

How it works:

Each person in the frame gets an ID (0, 1, 2…)
Every frame, you call validator.update(person_id, flagged=True/False)
It counts consecutive flagged frames per person
Only returns True (confirmed!) when the count hits 5 in a row
If the person stops being flagged, the counter resets to 0
"""

class FrameValidator:
    """
    Requires `required_frames` consecutive detections before confirming an incident.
    Resets the counter whenever detection disappears.
    """

    def __init__(self, required_frames: int = 5):
        self.required_frames = required_frames
        # counters[person_id] = number of consecutive frames flagged
        self.counters: dict[int, int] = {}

    def update(self, person_id: int, flagged: bool) -> bool:
        """
        Call once per frame per person.
        Returns True when this person has been CONFIRMED (hit the threshold).
        """
        if flagged:
            self.counters[person_id] = self.counters.get(person_id, 0) + 1
        else:
            # Reset if the detection disappears
            self.counters[person_id] = 0

        return self.counters.get(person_id, 0) >= self.required_frames

    def reset(self, person_id: int):
        """Call after an incident has been fired so it doesn't re-trigger immediately."""
        self.counters[person_id] = 0

    def get_count(self, person_id: int) -> int:
        return self.counters.get(person_id, 0)
