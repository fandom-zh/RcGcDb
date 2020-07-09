from dataclasses import dataclass

@dataclass
class Wiki:
	fail_times: int = 0  # corresponding to amount of times connection with wiki failed for client reasons (400-499)
