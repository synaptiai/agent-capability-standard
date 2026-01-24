# Drift detection rubric

Drift is divergence between the digital twin model and observed reality.

## Drift categories
1) **State drift**
   - observed state deviates beyond tolerance (e.g. error rate, latency)
2) **Transition drift**
   - transitions occur without expected triggers OR triggers occur without transitions
3) **Identity drift**
   - entity resolution collisions rise; alias confusion increases
4) **Schema drift**
   - events/observations no longer fit canonical schema (new fields, missing fields)
5) **Causal drift**
   - intervention effects differ from expected (policy no longer produces outcome)

## Drift signals (examples)
- metric threshold violations
- unexpected sequence patterns
- rising uncertainty over time
- conflict rate in `integrate` step
- increase in unknown entity references

## Outputs
- drift score (0–1)
- top contributing factors
- recommended actions (observe more, re-train transition rules, or act)
