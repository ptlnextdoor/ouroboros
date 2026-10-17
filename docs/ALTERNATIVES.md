# Alternatives considered

## A. GPU-tuning agent team (a friend's proposal), score 6.5/10
Agents on Crusoe find a bottleneck in an inference server on our A100s, propose configuration or
kernel experiments, challenge the results, and update an engineering playbook. An independent
evaluator accepts a change only when frozen checks pass (latency, correctness, memory). v1 vs v2
agents are compared on unseen workloads with equal budgets.

**Strengths**
- Speaks directly to Crusoe's business (inference performance).
- Metrics are measured, not judged by an LLM. Experiments are cheap (minutes each).
- The independent evaluator matters: published "AI kernel engineer" speedups have been
  partly explained by the model exploiting a weak evaluator.

**Why we didn't pick it as the main project**
- Most vLLM tuning is flag search, where Optuna or Bayesian optimization is a strong baseline. The agents
  would need to beat that baseline given the same budget.
- v1 vs v2 on unseen workloads gives only a few episodes per version in a day, so the
  comparison is statistically underpowered.
- The first big speedups usually come from fixing bad defaults, not from learning.
- Kernel work doesn't fit in 6 hours.

**If we had chosen it:** the playbook is what improves. The metric is *experiments-to-target on
an unseen workload vs Optuna with an equal budget*. Keep scope to config and serving, no kernels.

**Possible merge:** the tuning agents could speed up the vLLM server that Ouroboros samples
from, so the system makes its own training loop faster. Out of scope for the day.

## B. Simple prompt-evolution team (DSPy / Promptbreeder-style)
Easy to build, and many teams will do it. Few judges would call it original. We keep it as the
*fast loop* inside Ouroboros instead of the headline.

## C. GRPO / online RL
Rejected for the time budget. See [RESEARCH.md](RESEARCH.md) [6.2]: most of GRPO's edge comes
from filtering prompts, which we get with difficulty-filtered rejection sampling.
