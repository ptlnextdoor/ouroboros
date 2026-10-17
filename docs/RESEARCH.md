# I am designing a self-improving LLM agent system to build in a single 6-hour hac

**Question:** I am designing a self-improving LLM agent system to build in a single 6-hour hackathon, using 8x A100 80GB GPUs plus a hosted inference API. The system: a strong hosted model writes tasks and unit tests (verifier), a small open model (~4-9B, e.g. NVIDIA Nemotron Nano) attempts tasks, verified-correct trajectories are used to fine-tune (LoRA) the small model, and a new generation is promoted only if it beats its parent on a held-out benchmark. A faster outer loop also rewrites prompts/playbooks. Please synthesize the evidence on:
1) Self-training / expert iteration from verified outputs (STaR, ReST/ReST-EM, rejection sampling fine-tuning, RFT): how big are gains per iteration for code/math, how many iterations before plateau, how much data is needed, and failure modes (model collapse, diversity loss, overfitting to easy problems).
2) RL with verifiable rewards (GRPO, RLVR) vs expert iteration for small models: sample efficiency, stability, compute needed, and whether gains are achievable in a few GPU-hours.
3) Self-generated tasks and tests (self-play, CodeT, absolute-zero style, self-instruct for code): risks of incorrect generated tests, reward hacking, and verification methods to mitigate (test validation, multiple independent verifiers, mutation testing).
4) Automated prompt/agent optimization (DSPy, OPRO, TextGrad, Promptbreeder, ADAS, Gödel agent, Darwin Gödel Machine, AlphaEvolve-style evolutionary search): measured gains and overfitting to the dev set.
5) Statistically sound evaluation for promotion gates: held-out sets, benchmark contamination, minimum test-set sizes to detect 2-5 point gains, bootstrap/paired tests for comparing models on the same items.
6) Agent self-monitoring: detecting loops, drift, and premature 'done' claims; LLM-as-judge reliability and verifier agreement.
Output: concrete recommendations and quantitative expectations (effect sizes, iteration counts, sample sizes) for maximizing probability that a measurable before/after improvement shows up within ~4 hours of compute, and the most likely ways such a pipeline fails.

# A **4-Hour** Self-Improvement Plan

For a **single 6-hour hackathon** with 8×A100s, the evidence supports betting on **expert iteration / rejection-sampling fine-tuning**, lightweight prompt optimization, and strict held-out promotion gates, not a full RLVR stack. The strongest recurring pattern is that self-training from verified positives gives meaningful gains after **one to two iterations**, while RLVR can work but usually needs more rollout engineering, more samples, and tighter reward design to be reliable on short timelines [[1.1]](https://consensus.app/papers/teaching-large-language-models-to-reason-with-havrilla-du/e08df5d279d9568d90523c5003df2947/) [[2.1]](https://consensus.app/papers/beyond-human-data-scaling-selftraining-for-singh-co-reyes/efc517cb6ea75d3787a55701123249a5/) [[3.1]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) [[4.1]](https://consensus.app/papers/adastar-adaptive-data-sampling-for-training-selftaught-koh-oh/af4841439d425089a6a538ecebbe3fe7/).

## Self-Training

Verified-output self-training improves code and math performance, and the **largest gains usually come early**. ReST-EM reports significant gains on math and APPS code, but improvement diminishes after **a couple of iterations**, which the authors attribute to overfitting on a small set of training problems [[2.2]](https://consensus.app/papers/beyond-human-data-scaling-selftraining-for-singh-co-reyes/efc517cb6ea75d3787a55701123249a5/) [[2.1]](https://consensus.app/papers/beyond-human-data-scaling-selftraining-for-singh-co-reyes/efc517cb6ea75d3787a55701123249a5/). In agentic settings, two ReST-style iterations were enough to distill a much smaller model to performance comparable to a much larger prompted model on compositional QA [[5.1]](https://consensus.app/papers/rest-meets-react-selfimprovement-for-multistep-reasoning-aksitov-miryoosefi/c7214df6406a56efa067256f6fb22736/) [[5.2]](https://consensus.app/papers/rest-meets-react-selfimprovement-for-multistep-reasoning-aksitov-miryoosefi/c7214df6406a56efa067256f6fb22736/).

- **Iteration budget:** Plan for **1–2 training generations**, not many more; plateau after that is common [[2.1]](https://consensus.app/papers/beyond-human-data-scaling-selftraining-for-singh-co-reyes/efc517cb6ea75d3787a55701123249a5/) [[5.2]](https://consensus.app/papers/rest-meets-react-selfimprovement-for-multistep-reasoning-aksitov-miryoosefi/c7214df6406a56efa067256f6fb22736/).
- **Data need:** Even **~1,000 verified examples** can support measurable improvement for small-model reasoning pipelines [[3.2]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) [[3.3]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/).
- **Failure mode:** Positive-only filtering can over-train on **easy solved examples** and miss harder cases unless sampling is balanced by diversity or difficulty [[4.2]](https://consensus.app/papers/adastar-adaptive-data-sampling-for-training-selftaught-koh-oh/af4841439d425089a6a538ecebbe3fe7/) [[4.3]](https://consensus.app/papers/adastar-adaptive-data-sampling-for-training-selftaught-koh-oh/af4841439d425089a6a538ecebbe3fe7/) [[1.2]](https://consensus.app/papers/teaching-large-language-models-to-reason-with-havrilla-du/e08df5d279d9568d90523c5003df2947/).

## RLVR Versus Expert Iteration

RLVR and expert iteration often end up **closer than expected** on small-model reasoning. In a direct comparison, expert iteration performed best in most settings, and its sample complexity was reported as similar to PPO, with convergence requiring at most on the order of **10^6 samples** from a pretrained checkpoint, while another passage in the same paper says only **a few thousand samples** were needed in some settings [[1.3]](https://consensus.app/papers/teaching-large-language-models-to-reason-with-havrilla-du/e08df5d279d9568d90523c5003df2947/) [[1.4]](https://consensus.app/papers/teaching-large-language-models-to-reason-with-havrilla-du/e08df5d279d9568d90523c5003df2947/) [[1.5]](https://consensus.app/papers/teaching-large-language-models-to-reason-with-havrilla-du/e08df5d279d9568d90523c5003df2947/). A 2025 math study found simple rejection-sampling fine-tuning competitive with GRPO and PPO on 7B models, with GRPO averaging **56.3** across three benchmarks versus **52.3** for RAFT and **56.4** for Reinforce-Rej, suggesting much of GRPO’s gain comes from filtering bad prompts rather than sophisticated credit assignment [[6.1]](https://consensus.app/papers/a-minimalist-approach-to-llm-reasoning-from-rejection-xiong-yao/186e577bf4e65d668e6f3be8dc8949c7/) [[6.2]](https://consensus.app/papers/a-minimalist-approach-to-llm-reasoning-from-rejection-xiong-yao/186e577bf4e65d668e6f3be8dc8949c7/) [[6.3]](https://consensus.app/papers/a-minimalist-approach-to-llm-reasoning-from-rejection-xiong-yao/186e577bf4e65d668e6f3be8dc8949c7/).

| Feature | Result / Value |
|---|---|
| Study Type | RLVR training on small math models [[3.4]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |
| Hardware | **8× A100 80GB** for SFT and RLVR [[3.5]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |
| SFT Data | **1,107** verified problems [[3.3]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |
| RLVR Steps | **256** total, with gains saturating around **128** [[3.1]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |
| Rollouts | **16 rollouts × 16 prompts** per update [[3.6]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |
| Key Result | Difficulty filtering gave up to **+12%** in **less than half** the training steps of standard GRPO [[3.7]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) |

**Figure 1:** Compact RLVR compute and convergence expectations on small models

## Tasks And Tests

Self-generated tests are useful, but **test quality is the central failure point**. Solver-verifier work warns that naive training on self-generated data can accumulate errors and even collapse generalization if the synthetic problems or tests are too simple or wrong [[7.1]](https://consensus.app/papers/learning-to-solve-and-verify-a-selfplay-framework-for-code-lin-shen/6e2a88278da65ff6b5ec60380685e619/) [[7.2]](https://consensus.app/papers/learning-to-solve-and-verify-a-selfplay-framework-for-code-lin-shen/6e2a88278da65ff6b5ec60380685e619/). Self-play papers identify **self-collusion** as the main risk when one model writes both code and tests, because white-box access can produce trivial tests that maximize reward without probing correctness [[8.1]](https://consensus.app/papers/codea1-adversarial-evolving-of-code-llm-and-test-llm-via-wang-yan/308b7a245af2584ea68d3d80bac2d910/) [[8.2]](https://consensus.app/papers/codea1-adversarial-evolving-of-code-llm-and-test-llm-via-wang-yan/308b7a245af2584ea68d3d80bac2d910/).

- Use **separate solver and tester roles** or at least separate prompts/models to reduce collusion [[8.3]](https://consensus.app/papers/codea1-adversarial-evolving-of-code-llm-and-test-llm-via-wang-yan/308b7a245af2584ea68d3d80bac2d910/) [[8.2]](https://consensus.app/papers/codea1-adversarial-evolving-of-code-llm-and-test-llm-via-wang-yan/308b7a245af2584ea68d3d80bac2d910/).
- Validate tests by **cross-executing multiple candidate solutions** and preferring tests that discriminate among them [[9.1]](https://consensus.app/papers/cosplay-cooperative-selfplay-at-testtime-with-hu-liu/e8cb2293734e5f83be2cddfb230608de/) [[7.3]](https://consensus.app/papers/learning-to-solve-and-verify-a-selfplay-framework-for-code-lin-shen/6e2a88278da65ff6b5ec60380685e619/).
- Prefer **adversarial or failure-seeking tests** once the solver becomes moderately strong, because ordinary verifier tests start confirming semantics rather than exposing remaining bugs [[10.1]](https://consensus.app/papers/ace-selfevolving-llm-coding-framework-via-adversarial-huang-yu/6e7b9929351e53749fa67ff902d54608/) [[10.2]](https://consensus.app/papers/ace-selfevolving-llm-coding-framework-via-adversarial-huang-yu/6e7b9929351e53749fa67ff902d54608/).

## Prompt And Evaluation Loops

Automated prompt optimization can produce fast gains, but it is **dev-set optimization** and should be treated like model training. DSPy reports improvements over standard prompting of **over 25%** with GPT-3.5 and **65%** with Llama2-13B-chat, often within minutes of compilation, while Promptbreeder and APO also show substantial gains from iterative prompt search or editing [[11.1]](https://consensus.app/papers/dspy-compiling-declarative-language-model-calls-into-khattab-singhvi/6844ad2881555c45abd5aac1e4a464e4/) [[12.1]](https://consensus.app/papers/promptbreeder-selfreferential-selfimprovement-via-fernando-banarse/b55b1da0555c557cbafe89639ecb8005/) [[13.1]](https://consensus.app/papers/automatic-prompt-optimization-with-gradient-descent-and-pryzant-iter/924a7702577c534fa6a290345c30c6ee/). SePO reports an average **+4.49 point** gain over Manual-CoT across five benchmarks, supporting the idea that a fast outer loop over prompts can help in a hackathon-scale build [[14.1]](https://consensus.app/papers/sepo-selfevolving-prompt-agent-for-system-prompt-tao-wu/cab67faec8725b7b8f4e7a084fdf4460/).

Promotion should use a **strict held-out benchmark** disjoint from prompt search and training tasks, because repeated prompt or policy selection will otherwise overfit that dev set. For paired model comparisons on the same items, the supplied RLVR evaluation work uses **paired tests over per-prompt outcomes** across multiple random seeds, which is the right direction for your gate [[15.1]](https://consensus.app/papers/discounted-betabernoulli-reward-estimation-for-kim-ryu/b43c7f2a52f95fabbd3dde2e4eee10df/) [[15.2]](https://consensus.app/papers/discounted-betabernoulli-reward-estimation-for-kim-ryu/b43c7f2a52f95fabbd3dde2e4eee10df/). A practical implication is that detecting **2–5 point absolute gains** needs more held-out items than most hackathon demos use; if scores are binary pass/fail, a few dozen items is rarely enough for confidence, so promotion should require both a point gain and a paired significance check.

## Recommendations

- **Core loop:** Use hosted model task/test writing, small-model sampling, **verified-positive LoRA**, and promotion on a locked held-out set.
- **Compute target:** Expect the clearest win from **1 SFT baseline + 1 self-training round**; treat round 2 as optional.
- **Data target:** Aim for **~1,000–3,000** verified trajectories with balanced difficulty, not the largest possible pool [[3.3]](https://consensus.app/papers/online-difficulty-filtering-for-reasoning-oriented-bae-hong/31db173d0cec5fa093996f5fbe4501f1/) [[4.3]](https://consensus.app/papers/adastar-adaptive-data-sampling-for-training-selftaught-koh-oh/af4841439d425089a6a538ecebbe3fe7/).
- **Expected gain:** A realistic hackathon win is **small-to-moderate absolute improvement**, not DeepSeek-style jumps; bigger wins usually need stronger curricula, more iterations, or better verifiers [[16.1]](https://consensus.app/papers/vstar-training-verifiers-for-selftaught-reasoners-hosseini-yuan/cb5bb5757ed9548887409570cd808845/) [[17.1]](https://consensus.app/papers/coevolving-llm-coder-and-unit-tester-via-reinforcement-wang-yang/44e78ed80f065d73822b79d4eb30082c/) [[10.3]](https://consensus.app/papers/ace-selfevolving-llm-coding-framework-via-adversarial-huang-yu/6e7b9929351e53749fa67ff902d54608/).

The most likely failure modes are **bad tests**, **selection overfitting**, **training on easy positives**, and **RL complexity outrunning the clock**. For maximizing the chance of a measurable before/after improvement within **~4 hours of compute**, the best-supported design is a simple verified-trajectory self-training loop with adaptive sampling, separate test generation, and conservative promotion gates.
 
_These search results were found and analyzed using Consensus, an AI-powered search engine for research. Try it at https://consensus.app. © 2026 Consensus NLP, Inc. Personal, non-commercial use only; redistribution requires copyright holders’ consent._
 
## References
 
`1.` Havrilla A, Du Y, Raparthy S, et al. Teaching Large Language Models to Reason with Reinforcement Learning. *ArXiv.* 2024;abs/2403.04642. doi:10.48550/arxiv.2403.04642
 
> [1.1] We find that overall the simplest method, Expert Iteration ( EI ) (Anthony et al., 2017), performs best across all metrics for most reward setups and model initializations. (Introduction)
 
> [1.2] We identify the limited diversity of the dataset as a core reason for this. (Introduction)
 
> [1.3] Overall, we find all algorithms perform comparably, with Expert Iteration performing best in most cases. (Introduction)
 
> [1.4] Surprisingly, we find the sample complexity of Expert Iteration is similar to that of PPO, requiring at most on the order of 10 6 samples to converge from a pretrained checkpoint. (Introduction)
 
> [1.5] Surprisingly, EI is nearly as sample efficient as more sophisticated algorithms like Proximal Policy Optimization ( PPO ), both requiring only a few thousand samples to converge even when initialized from a pretrained checkpoint. (Introduction)
 
`2.` Singh A, Co-Reyes JD, Agarwal R, et al. Beyond Human Data: Scaling Self-Training for Problem-Solving with Language Models. *Trans. Mach. Learn. Res..* 2023;2024. doi:10.48550/arxiv.2312.06585
 
> [2.1] Interestingly, exceeding a couple of iterations of ReST 𝐸𝑀 leads to diminishing improvement, indicating potential overfitting on small amount of training problems (Figure 4). (Introduction)
 
> [2.2] Our empirical findings reveal significant advancements in both mathematical reasoning and code generation capabilities when applying ReST 𝐸𝑀 to PaLM 2 models of varying scales (Figure 1). (Introduction)
 
`3.` Bae S, Hong J, Lee MY, Kim H, Nam J, Kwak D. Online Difficulty Filtering for Reasoning Oriented Reinforcement Learning. 2025. doi:10.48550/arxiv.2504.03380
 
> [3.1] Training is run for 256 steps, with empirical performance gains saturating after roughly 128 steps. (Methods)
 
> [3.2] Only samples with verifiably correct solutions are retained, and we stop once approximately 1,000 such problem-solution pairs are collected. (Methods)
 
> [3.3] The final SFT dataset contains 1,107 filtered problems. (Methods)
 
> [3.4] All experiments are built on the Qwen2.5-3B base model (Yang et al., 2024b). (Methods)
 
> [3.5] Both the SFT and RLVR stages are conducted on a distributed setup of 8 × NVIDIA A100 (80GB) GPUs. (Methods)
 
> [3.6] Each update uses 16 sampled rollouts with 16 distinct prompts per batch, followed by a one-step policy update per rollout. (Methods)
 
> [3.7] Evaluations across multiple math reasoning benchmarks validate that balanced filtering consistently enhances convergence speed and final performance, achieving up to +12% gains in less than half the training steps of standard GRPO. (Abstract)
 
`4.` Koh W, Oh W, Jang J, et al. AdaSTaR: Adaptive Data Sampling for Training Self-Taught Reasoners. *ArXiv.* 2025;abs/2505.16322. doi:10.48550/arxiv.2505.16322
 
> [4.1] Self-Taught Reasoners (STaR), synonymously known as Rejection sampling Fine-Tuning (RFT), is an integral part of the training pipeline of self-improving reasoning Language Models (LMs). (Abstract)
 
> [4.2] However, this results in trained observation imbalance; inefficiently over-training on solved examples while under-training on challenging ones. (Abstract)
 
> [4.3] In response, we introduce Adaptive STaR (AdaSTaR), a novel algorithm that rectifies this by integrating two adaptive sampling principles: (1) Adaptive Sampling for Diversity: promoting balanced training across observations, and (2) Adaptive Sampling for Curriculum: dynamically adjusting data difficulty to match the model's evolving strength. (Abstract)
 
`5.` Aksitov R, Miryoosefi S, Li Z, et al. ReST meets ReAct: Self-Improvement for Multi-Step Reasoning LLM Agent. *ArXiv.* 2023;abs/2312.10003. doi:10.48550/arxiv.2312.10003
 
> [5.1] For example, Figure 1 provides a high-level overview of the agent performance on Bamboogle for different model sizes and showcases the boost with more iterations of ReST (all our synthetic data is produced with the large model, so for smaller models, it is the performance of the distillation). (Introduction)
 
> [5.2] Starting from a prompted large model and after just two iterations of the algorithm, we can produce a fine-tuned small model that achieves comparable performance on challenging compositional question-answering benchmarks with two orders of magnitude fewer parameters. (Abstract)
 
`6.` Xiong W, Yao J, Xu Y, et al. A Minimalist Approach to LLM Reasoning: from Rejection Sampling to Reinforce. *ArXiv.* 2025;abs/2504.11343. doi:10.48550/arxiv.2504.11343
 
> [6.1] | Model | Algorithm | Math500 | Minerva Math | Olympiad Bench | Average | |-----------------------|---------------|-----------|----------------|------------------|-----------| | Qwen2.5-Math-7B-base | Base | 41.3 | 11 | 18.6 | 23.6 | | | RAFT | 77.4 | 40.8 | 38.6 | 52.3 | | | RAFT++ | 80.2 | 44.9 | 43.3 | 56.1 | | | Iterative DPO | 76 | 31.2 | 39.3 | 48.8 | | | Reinforce | 80.1 | 40.7 | 40.9 | 53.9 | | | GRPO | 81.3 | 45.5 | 42.2 | 56.3 | | | PPO | 79 | 39.3 | 39.1 | 52.5 | | | Reinforce-Rej | 81.9 | 44.2 | 43.1 | 56.4 | (Methods)
 
> [6.2] Our ablation studies reveal that GRPO's main advantage arises from discarding prompts with entirely incorrect responses, rather than from its reward normalization. (Abstract)
 
> [6.3] Reinforce-Rej improves KL efficiency and stability, serving as a lightweight yet effective alternative to more complex RL algorithms. (Abstract)
 
`7.` Lin Z, Shen S, Kulikov I, Shang J, Weston JE, Nie Y. Learning to Solve and Verify: A Self-Play Framework for Code and Test Generation. *ArXiv.* 2025;abs/2502.14948. doi:10.48550/arxiv.2502.14948
 
> [7.1] Prior work has shown the potential of synthetic self-instruct data, but naively training on a model's own outputs can cause error accumulation, especially in coding tasks, where generalization may collapse due to overly simple or erroneous training data, highlighting the need for rigorous quality checks on synthetic data. (Introduction)
 
> [7.2] While previous work has shown significant improvements for models trained on data generated by larger, more competent models, training an LLM on its own generated data is not helpful and can even degrade performance (Zhou et al., 2024; Alemohammad et al., 2023). (Introduction)
 
> [7.3] It executes the generated code against these test cases and employs a dual execution agreement strategy, ensuring both output consistency and agreement among multiple code solutions. (Introduction)
 
`8.` Wang A, Yan Y, Zhou N, et al. Code-A1: Adversarial Evolving of Code LLM and Test LLM via Reinforcement Learning. *ArXiv.* 2026;abs/2603.15611. doi:10.48550/arxiv.2603.15611
 
> [8.1] Recent self-play methods unify code and test generation in a single model, but face a inherent dilemma: white-box access leads to self-collusion where the model produces trivial tests for easy rewards, yet black-box restriction yields generic tests that miss implementation-specific bugs. (Abstract)
 
> [8.2] This architectural separation eliminates self-collusion risks and safely enables white-box test generation, where the Test LLM can inspect candidate code to craft targeted adversarial tests. (Abstract)
 
> [8.3] We introduce Code-A1, an adversarial co-evolution framework that jointly optimizes a Code LLM and a Test LLM with opposing objectives. (Abstract)
 
`9.` Hu Z, Liu C, Huang T, et al. CoSPlay: Cooperative Self-Play at Test-Time with Self-Generated Code and Unit Test. *ArXiv.* 2026;abs/2605.23491. doi:10.48550/arxiv.2605.23491
 
> [9.1] It then uses bidirectional pass-count signals from the Code-UT execution matrix to iteratively prune or fix weak codes and refresh or replace unreliable UTs, letting the two pools co-evolve. (Abstract)
 
`10.` Huang Y, Yu X, Wei Z. ACE: Self-Evolving LLM Coding Framework via Adversarial Unit Test Generation and Preference Optimization. *ArXiv.* 2026;abs/2605.16299. doi:10.48550/arxiv.2605.16299
 
> [10.1] Recent solververifier frameworks exploit program execution as an automatic supervision signal, but their effectiveness degrades as solvers become moderately strong: verifiergenerated tests increasingly confirm semantic correctness rather than exposing the remaining failure modes. (Abstract)
 
> [10.2] Experiments on CodeContests, MBPP, and LiveCodeBench demonstrate that ACE consistently outperforms strong solver-verifier baselines, achieving 3-7% absolute gains in pass@1, with larger improvements on out-ofdistribution benchmarks, while maintaining competitive or improved inference efficiency. (Abstract)
 
> [10.3] Experiments on CodeContests, MBPP, and LiveCodeBench demonstrate that ACE consistently outperforms strong solver--verifier baselines, achieving 3--7\% absolute gains in pass@1, with larger improvements on out-of-distribution benchmarks, while maintaining competitive or improved inference efficiency. (Abstract)
 
`11.` Khattab O, Singhvi A, Maheshwari P, et al. DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines. *ArXiv.* 2023;abs/2310.03714. doi:10.48550/arxiv.2310.03714
 
> [11.1] Within minutes of compiling, a few lines of DSPy allow GPT-3.5 and llama2-13b-chat to self-bootstrap pipelines that outperform standard few-shot prompting (generally by over 25% and 65%, respectively) and pipelines with expert-created demonstrations (by up to 5-46% and 16-40%, respectively). (Abstract)
 
`12.` Fernando C, Banarse D, Michalewski H, Osindero S, Rocktäschel T. Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution. 2023. doi:10.48550/arxiv.2309.16797
 
> [12.1] In this paper, we present Promptbreeder, a general-purpose self-referential self-improvement mechanism that evolves and adapts prompts for a given domain. (Abstract)
 
`13.` Pryzant R, Iter D, Li J, Lee Y, Zhu C, Zeng M. Automatic Prompt Optimization with "Gradient Descent" and Beam Search. 2023. doi:10.48550/arxiv.2305.03495
 
> [13.1] Preliminary results across three benchmark NLP tasks and the novel problem of LLM jailbreak detection suggest that Automatic Prompt Optimization can outperform prior prompt editing techniques and improve an initial prompt's performance by up to 31%, by using data to rewrite vague task descriptions into more precise annotation instructions. (Abstract)
 
`14.` Tao W, Wu H, Wong W. SePO: Self-Evolving Prompt Agent for System Prompt Optimization. *ArXiv.* 2026;abs/2606.04465. doi:10.48550/arxiv.2606.04465
 
> [14.1] Across five benchmarks spanning math (AIME'25), abstract reasoning (ARC-AGI-1), graduate-level science (GPQA), code generation (MBPP), and logic puzzles (Sudoku), SePO consistently outperforms Manual-CoT, TextGrad, and MetaSPO, improving the average accuracy by 4.49 points compared to Manual-CoT. (Abstract)
 
`15.` Kim H, Ryu S, Chu G, Jang D, Yang E. Discounted Beta-Bernoulli Reward Estimation for Sample-Efficient Reinforcement Learning with Verifiable Rewards. *ArXiv.* 2026;abs/2603.18444. doi:10.48550/arxiv.2603.18444
 
> [15.1] For evaluation, we conduct four independent runs per method with different random seeds, sampling 8 responses per query in each run (i.e., 32 responses per prompt in total). (Methods)
 
> [15.2] Each cell reports the mean and standard deviation across the four runs, and statistical significance is assessed via one-sided paired t -tests over per-prompt accuracies. (Methods)
 
`16.` Hosseini A, Yuan X, Whitammer ES, Courville AC, Sordoni A, Agarwal R. V-STaR: Training Verifiers for Self-Taught Reasoners. *ArXiv.* 2024;abs/2402.06457. doi:10.48550/arxiv.2402.06457
 
> [16.1] Running V-STaR for multiple iterations results in progressively better reasoners and verifiers, delivering a 4% to 17% test accuracy improvement over existing self-improvement and verification approaches on common code generation and math reasoning benchmarks with LLaMA2 models. (Abstract)
 
`17.` Wang Y, Yang L, Tian Y, Shen K, Wang M. Co-Evolving LLM Coder and Unit Tester via Reinforcement Learning. *ArXiv.* 2025;abs/2506.03136. doi:10.48550/arxiv.2506.03136
 
> [17.1] Our derived ReasonFlux-Coder-7B and 14B models improve code generation accuracy by 5.3% and Best-of-N accuracy by 9.0% after optimization on Qwen2.5-Instruct models, outperforming similarly sized Qwen-Coder, DeepSeek-Coder, and Seed-Coder. (Abstract)
