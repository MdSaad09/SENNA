"""The gate-eval cadence at a stage boundary. num_timesteps is global and cumulative
across stages (reset_num_timesteps=False), so a cadence anchored at an absolute step
would burst-evaluate on every vec-step at Stage B entry until it caught up — ~30
back-to-back 200-race evaluations, and a resumed Stage A would trivially plateau.
"""

from senna.train.callbacks import GateEvalCallback
from senna.train.gates import GateDecision
from senna.train.tracking import Tracker


class _Model:
    """Just enough of MaskablePPO for BaseCallback.init_callback."""

    def __init__(self, num_timesteps):
        self.num_timesteps = num_timesteps
        self.logger = None

    def get_env(self):
        return None


def test_gate_eval_cadence_anchors_to_the_stage_entry_step():
    evals = []

    def evaluate(step):
        evals.append(step)
        return GateDecision(passed=False, reason="stub", values={})

    callback = GateEvalCallback(
        evaluate, every_steps=100, tracker=Tracker(), save_last=lambda step: None
    )
    model = _Model(num_timesteps=1_500_000)  # entering stage B mid-run
    callback.init_callback(model)
    callback.on_training_start({}, {})

    for _ in range(60):
        model.num_timesteps += 2  # one 2-worker vec step
        assert callback.on_step()

    # one eval, a full cadence after entry — never a burst at the boundary
    assert evals == [1_500_100]
