# Thermal research factory

An agent team that repairs a thermal simulation that disagrees with real measurements. It keeps a change only if experiments it never used while making the fix support that change.

Status: proposal only. No code exists yet. These notes were written on 2026-10-17, before hacking started at 10:45 AM PT. Visual brief: [`brief/index.html`](brief/index.html).

## The idea

The long-term goal is an autonomous research team for engineering. Agents keep researching, testing ideas and improving hardware designs with very little human involvement.

The hackathon build takes on one narrow problem: a simulation that doesn't match real measurements. Say a simulation predicts that an electronics board reaches 40°C, but an experiment measures 50°C. The agents read the research, look for the cause of the error, propose changes to the model and test them. A separate evaluator then checks each change against experiments the agents never saw. A change stays only if that evidence supports it.

Each result decides what the agents investigate next. When a test fails, they can question their assumptions and try a different explanation.

This is the first piece of a larger research factory. Making simulations match measurements comes first. Discovering better physical designs comes later.

## Use case

The users are hardware engineers whose simulations don't match their test results. The first domain is electronics temperature. The agents investigate the mismatch, test fixes and check whether the corrected model predicts new measurements more accurately.

## The research loop

The agents propose the work. A separate controller owns the budget, the evidence records and the acceptance checks.

| Step | What happens | Output |
|---|---|---|
| 1. Read | Read the dataset documentation and relevant research. Establish the measured inputs, units and assumptions. Reserve whole test experiments before fitting a simple CPU model. | Research contract and frozen baseline |
| 2. Explain | Find where the baseline disagrees with measured temperatures. Record candidate explanations and the observation that would tell them apart. A plausible story alone does not identify a cause. | Competing hypotheses and the checks that separate them |
| 3. Test | The agent proposes the next experiment. The controller admits it if it fits the declared scope and remaining budget, then records the model version, inputs, outputs and failures. | Experiment specification and runner receipt |
| 4. Verify | Compare the frozen candidate and the baseline on the reserved experiments. Count the full cost of the research. A gain on development data is not an improvement claim until this check passes. | Independent comparison and a scoped conclusion |
| 5. Revise | Keep a model change only when its evidence supports it. If the research procedure itself changes, compare the old and new procedures on fresh tasks. Confirmation data that informed a revision becomes development data. | Versioned decision and a replayable evidence package |

A worker saying "done" does not count as acceptance. The final result needs a versioned model, saved observations, independent checks and a replay command.

## What success means

- The revised model predicts the reserved experiments better than the frozen baseline. We report error in °C, and every method uses the same data split and the same total budget.
- We compare against conventional model fitting, so the agents have to beat a standard parameter fit and not only the starting model.
- Failed attempts stay in the record.
- When the measurements can't separate two explanations, the result reports the uncertainty or both explanations instead of picking one.

The likely track is Done Means Done. Version N+1 would need separate evidence that the research procedure itself improves on fresh tasks.

## Data

We use the open MPSoC thermal-modeling dataset by Terraneo, Leva and Fornaciari (version 2.0, 2019, CC BY 4.0). It has 39 recorded experiments: 13 heater layouts, each run on a bare chip, with a heatsink, and with a heatsink plus fan. Each run logs voltage and current for all 16 heaters, 16 temperature channels at 1 kHz, and room temperature. That lets us drive a model with measured power, compare its output with measured temperatures, and hold out whole experiments for the evaluator.

Details, column layout and download steps: [`data/mpsoc-3345878/README.md`](data/mpsoc-3345878/README.md).

The dataset contains measurements only, no simulation. We write the starting model ourselves, likely a simple heat-flow model of the 4x4 heater grid. Its errors against the measurements will be real, but we choose how simple it starts, and that choice sets how large the first mismatch is.

## Compute

The first version needs only a small Python model on CPU plus hosted agent inference on Crusoe Managed Inference. It assumes no new GPU rental and no commercial solver license.

The A100s are optional. They could run many candidate models or parameter settings as one batch, or host a local open model as an extra research worker. We would measure one A100 against the CPU first and add more GPUs only if they make the experiments faster. With this dataset, the CPU may already be fast enough.

## Readiness at 9:30 AM PT, 2026-10-17

Ready:
- The dataset is downloaded, checked against its md5 and inspected. The column layout matches the authors' plotting script.
- Python 3.14 with NumPy and SciPy is installed locally.
- Claude Code and Codex are available for building.

Missing:
- A Crusoe API key. The agent loop can't run without one, and we still need to confirm that the chosen model handles tool calls.
- The baseline simulation. It isn't written yet.
- Time. Hacking runs 10:45 AM to 5:00 PM PT. A full build was estimated at 18 to 32 solo hours, so today's scope is one cooling setup, one model family and one complete loop.
- The DGX. SSH timed out at 9:28 AM and the required GPU allocator isn't installed. This build doesn't need it.

Not chosen yet: which cooling setup to use and which experiments to reserve for the evaluator.

## Plan for the day

1. Reserve the test experiments and fit the baseline.
2. Connect Crusoe and enforce an experiment budget.
3. Run the agent loop and the independent evaluation.
4. Show either a supported result or an honest inconclusive outcome.

## Risks

- Originality. Existing systems such as The Agentic Scientist (AI Scientist-v3, https://arxiv.org/html/2610.18933v1) and AutoRA (https://joss.theoj.org/papers/10.21105/joss.06839) already automate much of the research loop. Adding an evaluator, memory or a graph isn't new. The demo has to show this specific behavior: a change gets rejected on reserved experiments, and the agents change direction because of it.
- The runs are short, about 20 to 39 seconds, so the model has to handle transient heating and can't rely on steady state alone.
- This dataset covers electronics only. Other hardware and spacecraft are future work.

## Data attribution

Federico Terraneo, Alberto Leva and William Fornaciari, "An Open-hardware Platform for MPSoC Thermal Modeling", 2019 IEEE International Conference on Embedded Computer Systems: Architectures, Modeling and Simulation (SAMOS). Dataset version 2.0, https://zenodo.org/records/3345878, CC BY 4.0.
