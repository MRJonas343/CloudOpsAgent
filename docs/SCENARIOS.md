# Incident Scenarios

These scenarios are the reproducible acceptance catalog for the local Compose MVP. Each scenario should run against a clean or reset environment, produce deterministic evidence, and leave no persistent fault state. The exact thresholds are configuration, not undocumented assumptions.

## MVP vs Deferred

| Status | Scenarios |
|---|---|
| **MVP** | Unhealthy Application, Traffic Spike |
| **Deferred to V2** | High CPU, Memory Pressure, High Error Rate |

MVP includes only 2 scenarios. The remaining 3 are fully specified below but deferred to V2 to keep the MVP scope lean.

## Common Evidence Contract

Capture the scenario ID, setup command or fixture, timestamps, incident payload, expected and actual tool calls, observations, hypothesis, diagnosis, plan, risk and approval decision, execution result, metrics/health/log verification, cleanup result, and test output. Do not add credentials or personal paths.

## High CPU [DEFERRED TO V2]

**Symptoms:** CPU rises above the configured threshold, latency may increase, and health may remain initially healthy.

**Trigger/setup:** Start Compose, confirm baseline, enable the bounded high-CPU simulation on `app`, and record the configured threshold and duration.

**Expected investigation/tool calls:** `checkHealth()`, `collectMetrics()`, read-only application/process context, recent logs, and correlation of CPU with latency and traffic. No arbitrary shell or process kill.

**Diagnosis:** CPU saturation is supported only when the metric trend and related evidence agree; distinguish traffic-driven load from an isolated simulation.

**Remediation proposal:** Stop or reduce the bounded local load, or propose a narrowly scoped capacity action. Include rollback/no-op and expected recovery.

**Approval expectation:** Observation is Risk 0. A reversible load-control action may be Risk 1 under local policy; capacity or infrastructure change is Risk 2 and requires human approval.

**Verification:** Re-check CPU and latency metrics, `/health`, representative `/api/orders`, and logs. Return to investigation if CPU falls but errors persist.

**Cleanup:** Disable the simulation and restore baseline configuration; verify no residual load.

**Test evidence:** Detector test, graph path test, approval branch test, verification assertions, and measured run output.

## Memory Pressure [DEFERRED TO V2]

**Symptoms:** Memory usage trends toward or beyond threshold, allocation pressure or degraded responses appear, and logs may show warnings.

**Trigger/setup:** Enable the bounded memory-pressure fixture with a finite duration and configured ceiling.

**Expected investigation/tool calls:** health, memory metrics, error/latency metrics, recent logs, and read-only process or container context where available.

**Diagnosis:** Confirm sustained pressure and distinguish a fixture from a leak-like trend; do not claim a leak without evidence.

**Remediation proposal:** Stop the fixture or propose a bounded restart/resource change with rollback and verification.

**Approval expectation:** Stopping a local fixture can be Risk 1; restart or resource changes are Risk 2 unless a specific low-risk policy says otherwise.

**Verification:** Check memory trend, `/health`, representative orders, and logs for recurrence or restart errors.

**Cleanup:** Disable the fixture, wait for resources to settle, and reset the service if the test requires it.

**Test evidence:** Memory detector and threshold tests, denial-without-approval test, and full verification output.

## Unhealthy Application [MVP]

**Symptoms:** `/health` fails or reports degraded status; orders may fail; logs show the corresponding fault.

**Trigger/setup:** Enable the bounded unhealthy state and record the expected health response and duration.

**Expected investigation/tool calls:** `checkHealth()`, `collectMetrics()`, representative `/api/orders`, recent logs, and incident history if available.

**Diagnosis:** Identify the configured health failure and whether the application is otherwise responsive. Do not infer root cause from status alone.

**Remediation proposal:** Disable the fault, restart the local service, or propose a bounded recovery action with explicit scope and rollback.

**Approval expectation:** Fault reset may be Risk 1 under local policy; restart or deployment action is Risk 2 and requires approval.

**Verification:** `/health` must recover, `/api/orders` must behave correctly, metrics must stabilize, and logs must explain any residual errors.

**Cleanup:** Disable the unhealthy state and restore normal fixture state.

**Test evidence:** Health failure detection, API retrieval, approval/denial, recovery verification, and cleanup assertions.

## High Error Rate [DEFERRED TO V2]

**Symptoms:** Error rate exceeds threshold for a configured window; latency and logs identify affected endpoint or operation.

**Trigger/setup:** Enable deterministic order failures or an error-rate fixture with a known numerator, denominator, and duration.

**Expected investigation/tool calls:** request/error metrics, representative `/api/orders`, health, endpoint-specific logs, and recent change context if represented by the fixture.

**Diagnosis:** Confirm the rate calculation and affected scope; separate application errors from monitoring or transport errors.

**Remediation proposal:** Disable the failure fixture or propose a rollback/configuration change with blast radius, approval, and verification.

**Approval expectation:** Fixture reset can be Risk 1; rollback or configuration change is Risk 2. Risk 3 applies if the proposed action is broad or destructive.

**Verification:** Error rate returns below threshold, health is good, representative orders succeed, and logs show no unexplained error burst.

**Cleanup:** Disable failure injection and clear any generated test data.

**Test evidence:** Rate-window tests, false-positive baseline, plan schema test, approval test, and measured recovery output.

## Traffic Spike [MVP]

**Symptoms:** Request rate increases sharply, latency or saturation may rise, and error rate may follow.

**Trigger/setup:** Start the bounded local traffic generator with a fixed request count/rate and finite timeout.

**Expected investigation/tool calls:** traffic, latency, CPU/memory, health, order success/error metrics, and logs. The agent must not launch an unbounded generator.

**Diagnosis:** Correlate traffic with saturation and errors; distinguish a traffic-driven incident from a service regression.

**Remediation proposal:** In local MVP, stop or reduce the generator or propose a narrowly scoped safe local remediation. In the later AWS path, a capacity proposal may produce a Terraform plan that the agent explains to the user (no apply). The proposal must include exact scope, expected effect, rollback/no-op, and verification criteria.

**Approval expectation:** Stopping the local generator is Risk 1. Scaling or routing changes are Risk 2 and require human approval. The Terraform path is `terraform_validate()` -> `terraform_plan()` -> agent explains the plan to the user (no apply or destroy). Broad traffic controls or IAM changes are Risk 3/high-risk and require elevated review; they are not automatic remediation.

**Verification:** For local MVP, traffic returns to expected range, latency and saturation recover, health is good, orders behave correctly, and logs are clean or explained. For a Terraform scaling plan, the agent explains what the plan would do; CloudWatch metrics/logs provide evidence where available.

**Cleanup:** Stop the generator, reset the application, and confirm baseline metrics. For an AWS test, retain the plan/audit evidence.

**Test evidence:** Traffic fixture bounds, detector test, tool-call allowlist test, local MVP proposal or remediation test, Terraform plan digest test when enabled, and complete cleanup result.

## Scenario Template

Copy this template for future cases and keep the headings stable so the evaluation harness can extract evidence.

```markdown
## <Scenario Name>

**Symptoms:**

**Trigger/setup:** Include fixture, configuration, threshold, duration, and baseline.

**Expected investigation/tool calls:** List registered tools in order and expected evidence.

**Diagnosis:** State the evidence-supported cause and uncertainty; do not fabricate reasoning.

**Remediation proposal:** Include exact scope, risk, expected effect, rollback or no-op, and verification criteria.

**Approval expectation:** State whether approval is required and why.

**Verification:** Check metrics, health, and logs; state the return-to-investigation condition.

**Cleanup:** Restore the baseline and prove the fixture is inactive.

**Test evidence:** Link commands, fixtures, assertions, and measured results.
```

## Scenario Quality Gate

- [ ] The trigger is bounded, deterministic, and resettable.
- [ ] Baseline evidence is captured.
- [ ] Expected tool calls are explicit and registered.
- [ ] Diagnosis separates evidence from uncertainty.
- [ ] Risk, approval, scope, rollback/no-op, and expiry are explicit.
- [ ] Metrics, health, and logs are all checked after action.
- [ ] Failed verification can return to investigation.
- [ ] Cleanup proves the environment is restored.
- [ ] Results contain measured evidence and no invented evaluation numbers.
