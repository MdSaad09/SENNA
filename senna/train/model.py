"""MaskablePPO built from configs/training.yaml — the 5.6.1 table as code. The masks
need no wrapper: sb3-contrib fetches action_masks through the vec stack itself, and
VecNormalize forwards env_method, so the compliance architecture (F-16) rides along
untouched."""


def build_model(train_cfg: dict, venv, *, seed: int):
    from sb3_contrib import MaskablePPO

    ppo = train_cfg["ppo"]
    policy = train_cfg["policy"]
    return MaskablePPO(
        "MlpPolicy",
        venv,
        policy_kwargs={"net_arch": {"pi": list(policy["pi"]), "vf": list(policy["vf"])}},
        n_steps=ppo["n_steps"],
        batch_size=ppo["batch_size"],
        n_epochs=ppo["n_epochs"],
        learning_rate=ppo["learning_rate"]["start"],  # decayed by ScheduleCallback
        gamma=ppo["gamma"],
        gae_lambda=ppo["gae_lambda"],
        clip_range=ppo["clip_range"],
        ent_coef=ppo["ent_coef"]["start"],  # likewise
        vf_coef=ppo["vf_coef"],
        max_grad_norm=ppo["max_grad_norm"],
        seed=seed,
        device="cpu",  # the policy is tiny (5.6.1); CPU wheels are the pinned stack
        verbose=0,
    )
