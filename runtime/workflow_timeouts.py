"""Independent stage deadlines and a non-competing Harbor safety deadline."""
DEFAULT_STAGE_TIMEOUT_SEC = 4 * 60 * 60


class StageTimeoutError(TimeoutError):
    pass


class TotalTimeoutError(TimeoutError):
    pass


def harbor_timeout_sec(stages, stage_timeout_sec=DEFAULT_STAGE_TIMEOUT_SEC):
    # Reserve time outside model calls for activation, evidence collection,
    # repository snapshots, and the deployer's existing 7800-second service call.
    return (600 + len(stages) * (stage_timeout_sec + 900)
            + sum(7800 for stage in stages if stage["role"] == "deployer"))
