# Multi-Level Score Fusion for LTE Throughput Anomaly Detection

## Presentation-ready technical explanation using the final simulation results

---

# 1. The central idea

The pipeline does **not** create one anomaly score by blindly adding every flag and every model output.

Instead, it performs fusion in stages:

```text
Statistical methods
        ↓
Statistical anomaly score
        ↓
Production ML models
        ↓
ML evidence, confidence, impact, and ML score
        ↓
Statistical–ML row-level fusion
        ↓
One-second fused anomaly priority
        ↓
Temporal episode fusion
        ↓
Episode priority
        ↓
Operational incident consolidation
        ↓
Canonical incident priority for RCA
```

Each stage answers a different question:

| Stage | Main question |
|---|---|
| Statistical scoring | How abnormal is this sample according to interpretable statistical evidence? |
| ML scoring | How strongly do causal predictive models say that actual throughput is below expected throughput? |
| Row-level statistical–ML fusion | How bad is the degradation, and how much independent evidence supports it at this second? |
| Episode fusion | Is this a persistent or repeated anomaly episode rather than an isolated row? |
| Operational incident fusion | Do nearby compatible episodes represent one engineer-facing network incident? |
| RCA handoff | Which consolidated incidents deserve the highest investigation priority? |

The final system therefore separates three concepts:

$$
\text{Impact} \neq \text{Confidence} \neq \text{Priority}
$$

- **Impact** measures how serious the performance degradation is.
- **Confidence** measures how strongly independent evidence supports the detection.
- **Priority** combines impact and confidence for investigation ordering.

The same principle is applied at the row, episode, and operational-incident levels.

---

# 2. Final simulation scale

The final production run used:

- **32,238 LTE downlink samples**
- **271 drive-test sessions**
- **1-second sampling interval**
- **8,086 broad statistical anomaly candidates**
- **6,217 statistical RCA-handoff rows**
- **140 strict production-ML anomalies**
- **3,574 final row-level fused handoff anomalies**
- **2,824 rows retained inside strict final episodes**
- **1,429 strict final episodes**
- **1,382 operational RCA incidents**
- **15 incidents in the diverse presentation/RCA shortlist**

The final row-level fusion sources were:

| Fusion source | Rows | Share of final fused rows |
|---|---:|---:|
| Statistical only | 3,434 | 96.08% |
| Statistical + ML consensus | 136 | 3.81% |
| ML only, supervised | 4 | 0.11% |
| **Total** | **3,574** | **100%** |

This confirms the intended design:

> Statistical methods are the primary anomaly detectors. ML strengthens confidence and contributes only a very small supervised exception path.

---

# 3. Level 1 — Statistical methods before fusion

## 3.1 The raw statistical methods

The system retains several statistical views because they answer different questions.

### Absolute low-throughput reference

The fixed domain reference is:

$$
T_{\text{fixed}} = 10\text{ Mbps}
$$

A sample is flagged when:

$$
T_{\text{actual}} < 10\text{ Mbps}
$$

Simulation result:

- **5,549 rows**
- **17.21% of all LTE-DL samples**

This is an interpretable domain anchor, not the only detector.

---

## 3.2 Global 10th percentile

The global P10 threshold is the throughput value below which 10% of the full dataset lies.

$$
P_{10,\text{global}}
=
Q_{0.10}
\left(
T_{\text{actual}}
\right)
$$

Actual simulation threshold:

$$
P_{10,\text{global}} = 4.990\text{ Mbps}
$$

Simulation result:

- **3,224 rows**
- **10.00%**

This method adapts to the complete drive-test distribution.

---

## 3.3 Session-relative P10

For each drive-test session $s$:

$$
P_{10,s}
=
Q_{0.10}
\left(
T_{\text{actual}} \mid s
\right)
$$

A row is relatively weak when:

$$
T_i < P_{10,s(i)}
$$

The median session-P10 threshold across the simulation was:

$$
\operatorname{median}(P_{10,s}) = 7.008\text{ Mbps}
$$

Simulation result:

- **2,685 rows**
- **8.33%**

This method detects rows that are poor relative to their own session, even when different sessions have different throughput levels.

---

## 3.4 IQR lower fence

Throughput is positively skewed, so the IQR method operates in log space.

Define:

$$
X = \log(1+T)
$$

Then:

$$
IQR = Q_3(X)-Q_1(X)
$$

The lower fence is:

$$
L_X = Q_1(X)-1.5IQR
$$

Converted back to Mbps:

$$
L_T = \exp(L_X)-1
$$

Actual simulation threshold:

$$
L_T = 0.669\text{ Mbps}
$$

Simulation result:

- **1,279 rows**
- **3.97%**

This is an extreme lower-tail detector.

---

## 3.5 Robust MAD / modified-Z detector

The robust center is the median:

$$
m = \operatorname{median}(X)
$$

The median absolute deviation is:

$$
MAD = \operatorname{median}\left(|X-m|\right)
$$

The modified-Z score is:

$$
Z_i^{*}
=
0.6745
\frac{X_i-m}{MAD}
$$

The factor $0.6745$ makes the MAD-based score comparable with a standard-Z score under an approximately normal reference distribution because:

$$
\operatorname{median}(|Z|) \approx 0.6745
$$

The final lower-tail condition is:

$$
Z_i^{*} \le -3
$$

The value $-3$ is a **dimensionless robust-Z threshold**, not $-3$ dB.

Actual simulation throughput cutoff implied by this rule:

$$
T_{\text{MAD cutoff}} = 0.550\text{ Mbps}
$$

Simulation result:

- **1,145 rows**
- **3.55%**

---

## 3.6 Why P10, IQR, and MAD are retained but not triple-counted

The actual overlap confirms a nested structure:

$$
\text{MAD extreme tail}
\subset
\text{IQR extreme tail}
\subset
\text{Global P10}
$$

Actual overlap:

| Pair | Intersection | Union | Jaccard |
|---|---:|---:|---:|
| Global P10 vs IQR | 1,279 | 3,224 | 0.397 |
| Global P10 vs MAD | 1,145 | 3,224 | 0.355 |
| IQR vs MAD | 1,145 | 1,279 | 0.895 |

Therefore, these methods remain visible for interpretation but are grouped into one higher-level **LOW LEVEL** family during independent-evidence fusion.

---

# 4. The four independent statistical families

The statistical layer reduces many correlated flags into four independent detector families.

## Family 1 — Low level

Includes:

- fixed 10 Mbps;
- global P10;
- session P10;
- IQR;
- robust MAD.

Simulation result:

- **5,782 rows**
- **17.94%**

---

## Family 2 — Temporal change

Includes:

- rolling/local drop;
- previous-sample sudden drop.

Simulation result:

- **3,685 rows**
- **11.43%**

---

## Family 3 — Expected underperformance

Includes:

- radio-conditioned P75;
- RB-conditioned P75.

Simulation result:

- **1,480 rows**
- **4.59%**

---

## Family 4 — RB efficiency

A row is inefficient when:

- RB usage is reliable;
- RB demand is medium/high;
- throughput per RB is in the bottom 10% of comparable high-demand rows;
- actual throughput is also low.

Define:

$$
\eta_{\text{RB}}
=
\frac{T_{\text{actual}}}{RB_{\text{used}}}
$$

The bottom-tail reference is:

$$
\eta_{\text{RB,P10}}
=
Q_{0.10}
\left(
\eta_{\text{RB}}
\mid
\text{reliable medium/high RB usage}
\right)
$$

RB-efficiency severity is:

$$
S_{\text{RB efficiency}}
=
\operatorname{clip}
\left(
\frac{
\eta_{\text{RB,P10}}-\eta_{\text{RB}}
}{
\eta_{\text{RB,P10}}
},
0,
1
\right)
$$

Simulation result:

- **518 rows**
- **1.61%**

---

# 5. Level 1A — Building the standalone statistical score

The statistical score is built in several steps.

---

## 5.1 Strongest-trigger base score

Each meaningful detector mechanism provides a minimum score floor.

| Statistical mechanism | Minimum base score |
|---|---:|
| Any trigger | 15 |
| Fixed/low-level throughput | 25 |
| Sustained low window | 35 |
| Radio-limited degradation | 35 |
| Local/temporal drop | 50 |
| Reliable P75 underperformance | 55 |
| Severe P75 underperformance | 75 |

The base score is:

$$
B_{\text{stat}}
=
\max
\left(
B_1,B_2,\ldots,B_k
\right)
$$

The maximum is used instead of adding the floors because multiple flags may describe the same physical degradation.

---

## 5.2 Continuous statistical magnitude

The score then measures how severe the row is continuously.

### Actual/expected ratio severity

For a reliable expected-throughput reference:

$$
R
=
\frac{T_{\text{actual}}}{T_{\text{expected}}}
$$

$$
S_{\text{ratio}}
=
\operatorname{clip}
\left(
\frac{0.60-R}{0.60},
0,
1
\right)
$$

Interpretation:

- $R \ge 0.60$ gives zero ratio severity;
- $R \rightarrow 0$ gives maximum severity.

---

### Expected-minus-actual gap severity

$$
G
=
T_{\text{expected}}-T_{\text{actual}}
$$

$$
S_{\text{gap}}
=
\operatorname{clip}
\left(
\frac{G}{80},
0,
1
\right)
$$

A gap of 80 Mbps or more saturates this component.

---

### Absolute-low severity

$$
S_{\text{low}}
=
\operatorname{clip}
\left(
\frac{20-T_{\text{actual}}}{20},
0,
1
\right)
$$

This 20 Mbps reference is a severity scale, not another anomaly detector.

Examples:

- $T=20$ Mbps gives $S_{\text{low}}=0$;
- $T=10$ Mbps gives $S_{\text{low}}=0.5$;
- $T=0$ Mbps gives $S_{\text{low}}=1$.

---

### Temporal-drop severity

The drop reference is:

$$
D
=
\max
\left(
D_{\text{rolling median}},
D_{\text{previous sample}}
\right)
$$

$$
S_{\text{drop}}
=
\operatorname{clip}
\left(
\frac{D}{40},
0,
1
\right)
$$

A 40 Mbps or larger drop saturates this component.

---

### Combined magnitude

$$
M_{\text{stat}}
=
100
\left(
0.35S_{\text{ratio}}
+
0.25S_{\text{gap}}
+
0.25S_{\text{low}}
+
0.15S_{\text{drop}}
\right)
$$

RB-efficiency can create a minimum magnitude floor:

$$
M_{\text{stat}}
=
\max
\left(
M_{\text{stat}},
75S_{\text{RB efficiency}}
\right)
$$

---

## 5.3 Independent-family bonus

Let $N_f$ be the number of active independent statistical families.

$$
B_{\text{family}}
=
\operatorname{clip}
\left(
5\ln
\left[
1+\max(N_f-1,0)
\right],
0,
12
\right)
$$

Examples:

- one family: $0$;
- two families: $5\ln 2=3.47$;
- three families: $5\ln 3=5.49$;
- four families: $5\ln 4=6.93$.

The logarithmic form rewards independent agreement without allowing score explosion.

---

## 5.4 Context/evidence bonus

The evidence bonus is:

$$
B_{\text{context}}
=
\operatorname{clip}
\left(
3L
+
4H_{\text{RB}}
+
2C_{\text{CA}}
+
2E_{\text{event}}
+
2R_{\text{poor radio}},
0,
10
\right)
$$

where:

- $L$ is bounded low-tail nested-severity strength;
- $H_{\text{RB}}=1$ for high RB usage;
- $C_{\text{CA}}=1$ when CA is active;
- $E_{\text{event}}=1$ for relevant nearby mobility/RACH context;
- $R_{\text{poor radio}}=1$ for poor-radio context.

Context can support a case but cannot dominate the score because the entire term is capped at 10.

---

## 5.5 Raw statistical score

$$
S_{\text{stat,pre-cap}}
=
\max
\left(
B_{\text{stat}},
M_{\text{stat}}
\right)
+
B_{\text{family}}
+
B_{\text{context}}
$$

---

## 5.6 Low-RB uncertainty compression

Low throughput under low RB usage may represent low offered load rather than a network limitation.

When RB usage is reliably low and no strong radio/temporal explanation exists:

$$
S_{\text{low-RB}}
=
45
\left[
1-
\exp
\left(
-\frac{1.5S_{\text{stat,pre-cap}}}{45}
\right)
\right]
$$

This smoothly approaches 45 rather than creating a hard pile-up at exactly 45.

---

## 5.7 High-score soft compression

For non-catastrophic scores above 85:

$$
S_{\text{stat,soft}}
=
85
+
(95-85)
\left[
1-
\exp
\left(
-\frac{S_{\text{pre-cap}}-85}{10}
\right)
\right]
$$

This preserves ordering while approaching the non-catastrophic cap of 95.

---

## 5.8 Catastrophic override

A row can receive 100 only when:

$$
T_{\text{actual}} \le 1\text{ Mbps}
$$

$$
T_{\text{expected}} \ge 50\text{ Mbps}
$$

$$
RB_{\text{demand}}\in\{\text{medium, high}\}
$$

and:

$$
N_f \ge 2
$$

Then:

$$
S_{\text{stat}}=100
$$

---

## 5.9 Actual contribution audit

Among the final statistical anomaly rows:

| Component | Mean | Median | P90 | Nonzero share |
|---|---:|---:|---:|---:|
| Strongest-trigger base | 44.47 | 50.00 | 55.00 | 100% |
| Continuous magnitude | 55.74 | 55.80 | 82.74 | 100% |
| Independent-family bonus | 1.31 | 0.00 | 3.47 | 33.42% |
| Context/evidence bonus | 3.85 | 4.00 | 7.00 | 91.47% |

This confirms that:

$$
\text{Main evidence}
\gg
\text{Bonuses}
$$

The final score is driven by anomaly seriousness, not by accumulating context flags.

---

# 6. Worked statistical example from the actual simulation

Consider the real consensus anomaly at:

- `source_index = 56065`
- actual throughput:

$$
T_{\text{actual}}=2.275\text{ Mbps}
$$

The active statistical families were:

```text
LOW LEVEL
TEMPORAL CHANGE
EXPECTED UNDERPERFORMANCE
RB EFFICIENCY
```

Therefore:

$$
N_f=4
$$

The components were:

$$
S_{\text{ratio}}=0.9687
$$

$$
S_{\text{gap}}=1.0000
$$

$$
S_{\text{low}}=0.8862
$$

$$
S_{\text{drop}}=1.0000
$$

Magnitude:

$$
\begin{aligned}
M_{\text{stat}}
&=
100
\left(
0.35(0.9687)
+
0.25(1)
+
0.25(0.8862)
+
0.15(1)
\right)
\\
&=
96.06
\end{aligned}
$$

Strongest base:

$$
B_{\text{stat}}=75
$$

Independent-family bonus:

$$
B_{\text{family}}
=
5\ln(4)
=
6.93
$$

Context bonus:

$$
B_{\text{context}}=3.00
$$

Raw score:

$$
\begin{aligned}
S_{\text{stat,pre-cap}}
&=
\max(75,96.06)+6.93+3.00
\\
&=
105.99
\end{aligned}
$$

The row did not pass the catastrophic override, so high-end compression was applied:

$$
\begin{aligned}
S_{\text{stat}}
&=
85+10
\left[
1-
\exp
\left(
-\frac{105.99-85}{10}
\right)
\right]
\\
&=
93.77
\approx
93.8
\end{aligned}
$$

This example shows why the statistical score is not a simple flag count.

---

# 7. Level 2 — ML scoring before statistical–ML fusion

Only three production predictors participate in the final ML decision:

1. **HGB strict-causal temporal central predictor**
2. **HGB resource-conditioned central predictor**
3. **Calibrated resource Q75 predictor**

Two methods remain validation/context only:

- LSTM-Q50;
- Isolation Forest.

---

# 8. Why OOF predictions are essential

The data contains one-second samples inside drive-test sessions. A random row split would allow neighboring samples from the same session to appear in both training and validation.

The pipeline uses session-group out-of-fold prediction.

For row $i$ in session $g(i)$:

$$
\hat{T}_i
=
f_{-g(i)}(X_i)
$$

where $f_{-g(i)}$ is trained without the complete session containing row $i$.

The final run used:

$$
K=5
$$

group-aware folds.

Every one of the 32,238 rows receives an OOF prediction from a model that did not train on its session.

---

# 9. Actual predictive-model quality

| Model | Train $R^2$ | Held-out $R^2$ | Train MAE | Held-out MAE |
|---|---:|---:|---:|---:|
| HGB strict-causal temporal | 0.945 | 0.920 | 6.93 Mbps | 8.50 Mbps |
| HGB resource-conditioned | 0.936 | 0.899 | 7.63 Mbps | 9.76 Mbps |
| Calibrated resource Q75 | 0.836 | 0.809 | 12.42 Mbps | 13.75 Mbps |
| LSTM-Q50 validation comparator | 0.807 | 0.749 | 13.31 Mbps | 14.74 Mbps |

The temporal HGB is the strongest central predictor.

The resource HGB is slightly weaker but contributes a different mechanism view.

The Q75 model is not intended to minimize central-prediction error; it represents an upper achievable opportunity reference.

---

# 10. ML anomaly gate for each model

For model $m$:

$$
G_m
=
\hat{T}_m-T_{\text{actual}}
$$

$$
R_m
=
\frac{T_{\text{actual}}}{\hat{T}_m}
$$

$$
e_m
=
\log(1+T_{\text{actual}})
-
\log(1+\hat{T}_m)
$$

A model-specific magnitude gate requires:

$$
\hat{T}_m \ge 25\text{ Mbps}
$$

$$
G_m \ge 15\text{ Mbps}
$$

$$
R_m \le r_m
$$

with:

| Model | Ratio gate |
|---|---:|
| Resource Q75 | 0.40 |
| Resource HGB central | 0.40 |
| Temporal HGB central | 0.50 |

When RB usage is reliable, medium/high demand is also required.

The residual must be in the model’s OOF lower tail:

$$
e_m \le Q_{0.05}(e_m)
$$

A severe model case additionally requires:

$$
e_m \le Q_{0.01}(e_m)
$$

$$
T_{\text{actual}}\le5\text{ Mbps}
$$

$$
G_m\ge30\text{ Mbps}
$$

---

# 11. Continuous model evidence

For each model:

$$
S_{\text{ratio},m}
=
\operatorname{clip}
\left(
\frac{r_m-R_m}{r_m},
0,
1
\right)
$$

$$
S_{\text{gap},m}
=
\operatorname{clip}
\left(
\frac{G_m-15}{80-15},
0,
1
\right)
$$

Let $p_m$ be the empirical OOF percentile of the log residual. Then:

$$
S_{\text{tail},m}
=
\operatorname{clip}
\left(
\frac{0.10-p_m}{0.10},
0,
1
\right)
$$

Model evidence is:

$$
E_m
=
0.35S_{\text{ratio},m}
+
0.35S_{\text{gap},m}
+
0.30S_{\text{tail},m}
$$

Evidence becomes zero when:

- expected throughput is below 20 Mbps; or
- the expected-minus-actual gap is not positive.

---

# 12. ML reliability priors

The model evidence is weighted by model quality and role.

| Model | Reliability prior |
|---|---:|
| HGB strict-causal temporal | 0.95 |
| HGB resource-conditioned | 0.90 |
| Resource Q75 | 0.90 |
| LSTM context | 0.68 |
| Isolation Forest context | 0.55 |

Only production models enter final confidence.

The resource family combines two correlated resource models using a maximum:

$$
E_{\text{resource}}
=
\max
\left(
0.90E_{\text{Q75}},
0.90E_{\text{HGB resource}}
\right)
$$

The temporal family is:

$$
E_{\text{temporal}}
=
0.95E_{\text{HGB temporal}}
$$

LSTM and Isolation Forest do not become extra production families.

---

# 13. Standalone ML confidence

The two independent ML families are fused using noisy-OR:

$$
C_{\text{ML,base}}
=
1-
(1-E_{\text{resource}})
(1-E_{\text{temporal}})
$$

Then:

$$
C_{\text{ML}}
=
\operatorname{clip}
\left(
C_{\text{ML,base}}
+
0.08I_{\text{two families}}
+
0.03I_{\text{RB demand}},
0,
1
\right)
$$

The reported confidence is:

$$
Confidence_{\text{ML}}=100C_{\text{ML}}
$$

---

# 14. Standalone ML impact

For an active ML family:

$$
S_{\text{low}}
=
\operatorname{clip}
\left(
\frac{20-T_{\text{actual}}}{20},
0,
1
\right)
$$

$$
S_{\text{gap}}
=
\operatorname{clip}
\left(
\frac{\hat{T}-T_{\text{actual}}}{80},
0,
1
\right)
$$

$$
S_{\text{ratio}}
=
\operatorname{clip}
\left(
\frac{0.60-T_{\text{actual}}/\hat{T}}{0.60},
0,
1
\right)
$$

$$
I_{\text{ML family}}
=
100
\left(
0.25S_{\text{low}}
+
0.40S_{\text{gap}}
+
0.35S_{\text{ratio}}
\right)
$$

The final ML impact is the largest active production-family impact:

$$
I_{\text{ML}}
=
\max
\left(
I_{\text{resource}},
I_{\text{temporal}}
\right)
$$

---

# 15. Standalone ML anomaly score

$$
Score_{\text{ML}}
=
0.55I_{\text{ML}}
+
0.45Confidence_{\text{ML}}
$$

The score uses the same 55/45 philosophy later used by the full fusion.

---

# 16. Final strict ML gate

A row becomes a final production-ML anomaly when:

$$
N_{\text{ML families}}\ge2
$$

or when one family satisfies the strong-single condition:

$$
Confidence_{\text{ML}}\ge70
$$

$$
G_{\text{best}}\ge30\text{ Mbps}
$$

$$
R_{\text{best}}\le0.25
$$

$$
E_{\text{best}}\ge0.75
$$

and the model also satisfies severe residual-tail evidence.

Actual simulation results:

| ML method/output | Rows | Share |
|---|---:|---:|
| Q75 resource underperformance | 214 | 0.664% |
| HGB resource underperformance | 129 | 0.400% |
| HGB temporal underperformance | 227 | 0.704% |
| ML candidate gate | 322 | 0.999% |
| Final strict ML anomalies | 140 | 0.434% |
| Final ML-only retained | 4 | 0.012% |

All four ML-only cases require human review.

---

# 17. Worked ML example from the actual simulation

Use the same real row:

$$
T_{\text{actual}}=2.275\text{ Mbps}
$$

For the resource Q75 model:

$$
\hat{T}_{Q75}=47.774\text{ Mbps}
$$

$$
G_{Q75}=45.498\text{ Mbps}
$$

$$
R_{Q75}=0.04763
$$

$$
p_{Q75}=0.001117
$$

Ratio severity:

$$
S_{\text{ratio},Q75}
=
\frac{0.40-0.04763}{0.40}
=
0.8809
$$

Gap severity:

$$
S_{\text{gap},Q75}
=
\frac{45.498-15}{65}
=
0.4692
$$

Residual-tail severity:

$$
S_{\text{tail},Q75}
=
\frac{0.10-0.001117}{0.10}
=
0.9888
$$

Q75 evidence:

$$
\begin{aligned}
E_{Q75}
&=
0.35(0.8809)
+
0.35(0.4692)
+
0.30(0.9888)
\\
&=
0.7692
\end{aligned}
$$

After the reliability prior:

$$
0.90E_{Q75}
=
0.6923
$$

The resource-family evidence was:

$$
E_{\text{resource}}=0.6923
$$

The temporal-family evidence was:

$$
E_{\text{temporal}}=0.6261
$$

ML noisy-OR:

$$
\begin{aligned}
C_{\text{ML,base}}
&=
1-(1-0.6923)(1-0.6261)
\\
&=
0.8849
\end{aligned}
$$

With two-family and RB-demand bonuses:

$$
C_{\text{ML}}
=
0.8849+0.08+0.03
=
0.9949
$$

$$
Confidence_{\text{ML}}=99.49
$$

ML impact:

$$
I_{\text{ML}}=69.90
$$

ML score:

$$
\begin{aligned}
Score_{\text{ML}}
&=
0.55(69.90)+0.45(99.49)
\\
&=
83.22
\end{aligned}
$$

---

# 18. Level 3 — Statistical–ML row-level fusion

The row-level fusion does not average the statistical and ML scores.

Instead, it builds:

1. statistical evidence;
2. production-ML evidence;
3. fused confidence;
4. mechanism-aware row impact;
5. final row priority.

---

# 19. Statistical evidence used in final fusion

Let:

$$
S_{\text{stat,raw}}
=
\frac{\text{uncapped statistical analytical score}}{100}
$$

A reliability prior depends on the strongest statistical mechanism.

| Statistical mechanism | Reliability |
|---|---:|
| Reliable P75, RB efficiency, or strict CA | 1.00 |
| Radio-limited degradation | 0.92 |
| Temporal change | 0.90 |
| Sustained degradation | 0.82 |
| Low-tail only | 0.55 |
| Other/default | 0.65 |

Therefore:

$$
E_{\text{stat}}
=
\operatorname{clip}
\left(
S_{\text{stat,raw}},
0,
1
\right)
\times
R_{\text{stat}}
$$

This prevents a weak low-tail-only case from being treated as equally reliable as confirmed expected underperformance.

---

# 20. Production-ML evidence used in final fusion

The final ML evidence is the two-family noisy-OR:

$$
E_{\text{ML}}
=
1-
(1-E_{\text{resource}})
(1-E_{\text{temporal}})
$$

LSTM and Isolation Forest are excluded from this production fusion.

---

# 21. Fused row confidence

The statistical and ML evidence sources receive bounded ceilings:

$$
C_{\text{stat component}}
=
0.90E_{\text{stat}}
$$

$$
C_{\text{ML component}}
=
0.85E_{\text{ML}}
$$

The base fused confidence is:

$$
C_{\text{base}}
=
1-
(1-0.90E_{\text{stat}})
(1-0.85E_{\text{ML}})
$$

Then:

$$
C_{\text{row}}
=
\operatorname{clip}
\left(
C_{\text{base}}
+
0.07A
+
0.03R
+
0.03M_2,
0,
1
\right)
$$

where:

- $A=1$ when final statistical and final ML decisions agree;
- $R=1$ when RB demand is medium/high;
- $M_2=1$ when both production ML families support the row.

The reported value is:

$$
Confidence_{\text{row}}
=
100C_{\text{row}}
$$

---

# 22. Why the ceilings are 0.90 and 0.85

They are not estimated probabilities.

They express the governance rule that:

- statistical evidence is primary and directly interpretable;
- ML is strong support but carries prediction uncertainty;
- neither source alone should automatically imply certainty.

The selected production setting was tested against nearby alternatives:

| Statistical ceiling | ML ceiling | Incidents $\ge40$ | Top-50 overlap | Spearman correlation |
|---:|---:|---:|---:|---:|
| 0.85 | 0.80 | 1,380 | 86% | 0.964 |
| 0.85 | 0.85 | 1,380 | 88% | 0.966 |
| 0.85 | 0.90 | 1,380 | 88% | 0.967 |
| 0.90 | 0.80 | 1,381 | 82% | 0.956 |
| **0.90** | **0.85** | **1,381** | **82%** | **0.958** |
| 0.90 | 0.90 | 1,381 | 82% | 0.960 |
| 0.95 | 0.80 | 1,382 | 70% | 0.946 |
| 0.95 | 0.85 | 1,382 | 70% | 0.948 |
| 0.95 | 0.90 | 1,382 | 70% | 0.950 |

The ranking remains strongly correlated around the production setting, so the selected ceilings are stable enough to freeze without tuning them on the same data.

---

# 23. Mechanism-aware expected-throughput fusion

The pipeline does not compare actual throughput with the maximum of unrelated predictions.

It constructs three mechanism-specific expected references.

## Capability/radio reference

$$
T_{\text{capability}}
=
P75
\left(
T
\mid
\text{radio context}
\right)
$$

---

## Resource reference

$$
T_{\text{resource}}
=
\operatorname{median}
\left(
T_{\text{RB P75}},
T_{\text{ML resource Q75}},
T_{\text{HGB resource central}}
\right)
$$

---

## Temporal reference

$$
T_{\text{temporal}}
=
\operatorname{median}
\left(
T_{\text{HGB temporal central}},
T_{\text{rolling median}}
\right)
$$

---

# 24. Row impact by mechanism

For capability and resource:

$$
I_{\text{base}}
=
0.25S_{\text{low}}
+
0.40S_{\text{gap}}
+
0.35S_{\text{ratio}}
$$

For temporal impact:

$$
I_{\text{temporal}}
=
0.80I_{\text{base}}
+
0.20S_{\text{drop}}
$$

For radio-limited impact:

$$
I_{\text{radio}}
=
0.70S_{\text{low}}
+
0.30S_{\text{persistence proxy}}
$$

with:

$$
S_{\text{persistence proxy}}
=
0.70I_{\text{sustained}}
+
0.30I_{\text{bad session sample}}
$$

Only technically active families are evaluated.

The row impact is:

$$
I_{\text{row}}
=
100
\max
\left(
I_{\text{capability}},
I_{\text{resource}},
I_{\text{temporal}},
I_{\text{radio}}
\right)
$$

The family producing the maximum becomes the dominant impact family.

Actual dominant-family counts among the 3,574 final fused rows:

| Dominant impact family | Rows |
|---|---:|
| Radio | 1,421 |
| Capability | 1,115 |
| Temporal | 973 |
| Resource | 65 |

---

# 25. Final row priority

$$
Priority_{\text{row}}
=
0.55I_{\text{row}}
+
0.45Confidence_{\text{row}}
$$

The 55/45 weighting means:

- impact is slightly more important;
- confidence still meaningfully changes ranking;
- a severe but weakly supported event does not automatically dominate;
- a highly confident but mild event also does not automatically dominate.

Actual row-level final-priority distribution:

| Statistic | Priority |
|---|---:|
| Minimum | 50.00 |
| P25 | 59.18 |
| Median | 68.31 |
| P75 | 78.32 |
| P90 | 83.25 |
| P95 | 86.49 |
| P99 | 92.10 |
| Maximum | 98.96 |

---

# 26. Row-level keep paths

A final fused row enters through one of three paths.

## Statistical–ML consensus

The row has:

- statistical handoff evidence;
- a final production-ML anomaly;
- sufficient fused priority.

Actual result:

- **136 rows**

---

## Statistical-only retained

The row has a valid statistical mechanism:

- reliable P75/RB/CA underperformance;
- radio-limited planning case;
- significant temporal degradation.

Actual result:

- **3,434 rows**

---

## ML-only supervised

The row has no statistical handoff but satisfies:

$$
Confidence_{\text{row}}\ge55
$$

$$
Priority_{\text{row}}\ge50
$$

or a severe production-model override.

Actual result:

- **4 rows**
- all require human verification.

---

# 27. Worked statistical–ML fusion example

For the real row at `source_index = 56065`:

$$
I_{\text{row}}=96.06
$$

Statistical evidence:

$$
E_{\text{stat}}=1.0000
$$

Production-ML evidence:

$$
E_{\text{ML}}=0.8849
$$

Statistical component:

$$
0.90E_{\text{stat}}
=
0.9000
$$

ML component:

$$
0.85E_{\text{ML}}
=
0.7522
$$

Base noisy-OR:

$$
\begin{aligned}
C_{\text{base}}
&=
1-(1-0.9000)(1-0.7522)
\\
&=
0.9752
\end{aligned}
$$

Bonuses:

$$
0.07A+0.03R+0.03M_2
=
0.07+0.03+0.03
=
0.13
$$

Therefore:

$$
C_{\text{row}}
=
\operatorname{clip}(0.9752+0.13,0,1)
=
1
$$

$$
Confidence_{\text{row}}=100
$$

Final row priority:

$$
\begin{aligned}
Priority_{\text{row}}
&=
0.55(96.06)+0.45(100)
\\
&=
97.83
\end{aligned}
$$

This row is the strongest one-second sample used later inside an episode and operational incident.

---

# 28. Level 4 — Episode fusion

One-second rows are too granular for RCA.

The system groups nearby anomaly rows inside the same session when:

- timestamp gap is no more than 3 seconds;
- serving-cell identity remains compatible;
- timestamp order is valid.

`source_index` remains lineage only and is not a hard continuity splitter.

---

# 29. Episode persistence

For an episode:

## Longest uninterrupted run

$$
S_{\text{run}}
=
\operatorname{clip}
\left(
\frac{L_{\text{run}}}{10},
0,
1
\right)
$$

## Observed anomalous time

$$
S_{\text{time}}
=
\operatorname{clip}
\left(
\frac{T_{\text{anomalous}}}{20},
0,
1
\right)
$$

## Episode density

$$
Density
=
\frac{
T_{\text{anomalous}}
}{
T_{\text{inclusive span}}
}
$$

Episode persistence:

$$
P_{\text{episode}}
=
100
\left(
0.60S_{\text{run}}
+
0.25S_{\text{time}}
+
0.15Density
\right)
$$

Actual episode-persistence results:

| Statistic | Persistence |
|---|---:|
| Minimum | 16.00 |
| Median | 22.25 |
| P75 | 29.50 |
| P90 | 36.75 |
| P99 | 52.00 |
| Maximum | 100.00 |

---

# 30. High-quality direct-evidence coverage

Each row contributes at most one direct-evidence unit.

Examples of qualifying direct evidence:

- reliable P75 gap of at least 25 Mbps and ratio at most 0.25;
- RB-efficiency under high RB usage;
- strict CA underperformance under confirmed demand;
- radio-limited degradation with at least two poor-radio indicators and throughput no greater than 10 Mbps;
- local/sudden drop of at least 15 Mbps;
- two-family production-ML agreement with confidence at least 70.

Episode direct-evidence coverage is:

$$
E_{\text{episode}}
=
\frac{
N_{\text{high-quality evidence rows}}
}{
N_{\text{episode rows}}
}
$$

---

# 31. Episode impact

$$
I_{\text{episode}}
=
0.50I_{\text{row,max}}
+
0.25I_{\text{row,mean}}
+
0.25P_{\text{episode}}
$$

Interpretation:

- maximum impact protects short catastrophic drops;
- mean impact rewards consistent degradation;
- persistence rewards duration and density.

---

# 32. Episode confidence

Let:

$$
A_{\text{episode}}
=
\frac{
N_{\text{statistical–ML consensus rows}}
}{
N_{\text{episode rows}}
}
$$

Then:

$$
C_{\text{episode}}
=
0.50C_{\text{row,max}}
+
0.25C_{\text{row,mean}}
+
0.15A_{\text{episode}}
+
0.10E_{\text{episode}}
$$

---

# 33. Episode priority

$$
Priority_{\text{episode}}
=
0.55I_{\text{episode}}
+
0.45C_{\text{episode}}
$$

Normal handoff requires:

$$
Priority_{\text{episode}}\ge40
$$

and:

$$
C_{\text{episode}}\ge40
$$

A critical override is allowed only when:

$$
I_{\text{episode}}\ge80
$$

and high-quality direct evidence exists.

Actual gate results:

| Episode path | Episodes |
|---|---:|
| Normal priority-and-confidence gate | 1,362 |
| Critical verified-evidence override | 67 |
| **Final episodes** | **1,429** |

---

# 34. Worked episode example

The row-level example belongs to:

```text
LTE-TP-EP-001515
```

Episode properties:

- rows: 3;
- longest run: 3 seconds;
- observed anomalous time: 3 seconds;
- density: 1.0;
- maximum row impact: 96.06;
- mean row impact: 85.82;
- maximum row confidence: 100;
- mean row confidence: 87.33;
- statistical–ML agreement coverage: $1/3$;
- direct-evidence coverage: 1.0.

Persistence:

$$
\begin{aligned}
P_{\text{episode}}
&=
100
\left[
0.60\left(\frac{3}{10}\right)
+
0.25\left(\frac{3}{20}\right)
+
0.15(1)
\right]
\\
&=
36.75
\end{aligned}
$$

Episode impact:

$$
\begin{aligned}
I_{\text{episode}}
&=
0.50(96.06)
+
0.25(85.82)
+
0.25(36.75)
\\
&=
78.67
\end{aligned}
$$

Episode confidence:

$$
\begin{aligned}
C_{\text{episode}}
&=
0.50(100)
+
0.25(87.33)
+
0.15(33.33)
+
0.10(100)
\\
&=
86.83
\end{aligned}
$$

Episode priority:

$$
\begin{aligned}
Priority_{\text{episode}}
&=
0.55(78.67)
+
0.45(86.83)
\\
&=
82.35
\end{aligned}
$$

The one-second peak was 97.83, but the complete episode receives 82.35 because it incorporates average behavior and persistence.

---

# 35. Level 5 — Operational incident consolidation

Strict episodes are still not always the correct engineer-facing unit.

Two episodes can represent the same network problem when they are separated by a short recovery or internal gap.

Episodes are consolidated when they satisfy:

$$
\Delta t \le 5\text{ seconds}
$$

$$
\Delta d \le 50\text{ meters}
$$

plus:

- same session;
- compatible serving cell;
- compatible statistical, ML, or dominant impact family.

The final simulation consolidated:

$$
1429\text{ episodes}
\rightarrow
1382\text{ incidents}
$$

---

# 36. Incident persistence

Operational incidents include recurrence across strict episodes.

## Longest episode run

$$
S_{\text{incident run}}
=
\operatorname{clip}
\left(
\frac{L_{\max}}{10},
0,
1
\right)
$$

## Total anomalous time

$$
S_{\text{incident time}}
=
\operatorname{clip}
\left(
\frac{T_{\text{total anomalous}}}{20},
0,
1
\right)
$$

## Recurrence

$$
S_{\text{recurrence}}
=
\operatorname{clip}
\left(
\frac{N_{\text{strict episodes}}}{3},
0,
1
\right)
$$

Incident persistence:

$$
P_{\text{incident}}
=
100
\left(
0.50S_{\text{incident run}}
+
0.30S_{\text{incident time}}
+
0.20S_{\text{recurrence}}
\right)
$$

Actual incident-persistence distribution:

| Statistic | Persistence |
|---|---:|
| Minimum | 13.17 |
| Median | 16.17 |
| P75 | 19.67 |
| P90 | 26.17 |
| P99 | 47.96 |
| Maximum | 86.67 |

---

# 37. Incident impact

$$
I_{\text{incident}}
=
0.45I_{\text{episode,max}}
+
0.30I_{\text{episode,mean}}
+
0.25P_{\text{incident}}
$$

This balances:

- strongest episode;
- average episode seriousness;
- recurrence and total duration.

---

# 38. Incident confidence

Let:

$$
A_{\text{incident}}
=
\frac{
N_{\text{statistical–ML consensus rows}}
}{
N_{\text{incident rows}}
}
$$

and:

$$
E_{\text{incident}}
=
\frac{
N_{\text{high-quality direct-evidence rows}}
}{
N_{\text{incident rows}}
}
$$

Then:

$$
C_{\text{incident}}
=
0.50C_{\text{episode,max}}
+
0.30C_{\text{episode,mean}}
+
0.10A_{\text{incident}}
+
0.10E_{\text{incident}}
$$

---

# 39. Canonical operational incident priority

$$
Priority_{\text{incident}}
=
0.55I_{\text{incident}}
+
0.45C_{\text{incident}}
$$

The output field is:

```text
incident_final_priority_0_100
```

This is the **canonical priority handed to RCA**.

Actual distribution:

| Statistic | Incident priority |
|---|---:|
| Minimum | 34.31 |
| P25 | 51.90 |
| Median | 56.51 |
| P75 | 60.70 |
| P90 | 65.45 |
| P95 | 68.94 |
| P99 | 73.83 |
| Maximum | 78.41 |

Final incident severities:

| Severity | Incidents |
|---|---:|
| High | 147 |
| Medium | 1,224 |
| Low | 11 |
| **Total** | **1,382** |

---

# 40. Worked operational incident example

The worked episode belongs to:

```text
INC-001023
```

Incident properties:

- strict episodes: 1;
- rows: 3;
- maximum episode impact: 78.67;
- mean episode impact: 78.67;
- maximum episode confidence: 86.83;
- mean episode confidence: 86.83;
- agreement coverage: $1/3$;
- direct-evidence coverage: 1.0;
- longest run: 3 seconds;
- total anomalous time: 3 seconds.

Incident persistence:

$$
\begin{aligned}
P_{\text{incident}}
&=
100
\left[
0.50\left(\frac{3}{10}\right)
+
0.30\left(\frac{3}{20}\right)
+
0.20\left(\frac{1}{3}\right)
\right]
\\
&=
26.17
\end{aligned}
$$

Incident impact:

$$
\begin{aligned}
I_{\text{incident}}
&=
0.45(78.67)
+
0.30(78.67)
+
0.25(26.17)
\\
&=
65.55
\end{aligned}
$$

Incident confidence:

$$
\begin{aligned}
C_{\text{incident}}
&=
0.50(86.83)
+
0.30(86.83)
+
0.10(33.33)
+
0.10(100)
\\
&=
82.80
\end{aligned}
$$

Canonical incident priority:

$$
\begin{aligned}
Priority_{\text{incident}}
&=
0.55(65.55)
+
0.45(82.80)
\\
&=
73.31
\end{aligned}
$$

---

# 41. The complete priority chain

For the same real anomaly:

| Level | Priority | Meaning |
|---|---:|---|
| Peak one-second row | 97.83 | Maximum instantaneous anomaly seriousness |
| Episode | 82.35 | Severity after average behavior and episode persistence |
| Operational incident | 73.31 | Final engineer-facing score after incident persistence and evidence coverage |

The priority decreases because each aggregation level asks a broader question.

The row asks:

> How severe is this exact second?

The episode asks:

> How severe and convincing is the complete continuous anomaly period?

The incident asks:

> How important is the complete operational problem after recurrence, persistence, and evidence consistency are considered?

Across all 1,382 incidents, the actual simulation showed:

| Difference | Mean | Median |
|---|---:|---:|
| Peak row minus episode priority | 11.31 | 11.33 |
| Episode minus incident priority | 7.95 | 7.85 |
| Peak row minus incident priority | 19.26 | 19.19 |

This is expected.

A one-second catastrophic point remains visible, but it does not force the complete incident to inherit the same score.

---

# 42. Which priority is handed to RCA?

The RCA team receives:

```text
incident_final_priority_0_100
```

This is also referred to as:

- operational incident priority;
- canonical incident priority;
- final RCA priority.

These names refer to the same value.

The RCA handoff may also include:

```text
peak_row_priority_0_100
episode_adjusted_priority_0_100
```

but only as supporting context.

## Why incident priority is the correct handoff value

It:

- avoids handing off repeated one-second rows;
- incorporates complete episode behavior;
- incorporates recurrence across episodes;
- includes maximum and mean impact;
- includes maximum and mean confidence;
- accounts for direct-evidence coverage;
- produces one ranking value per operational problem;
- matches the compact RCA JSON and CSV;
- is validated to be identical across the operational and compact handoff files.

The full validated payload contains:

- **1,382 JSON incidents**
- **1,382 CSV incidents**
- **1,382 operational-summary incidents**
- exact incident-ID agreement;
- zero canonical-priority mismatch.

---

# 43. End-to-end funnel interpretation

The final flow is:

$$
32238
\rightarrow
8086
\rightarrow
6217
\rightarrow
140
\rightarrow
3574
\rightarrow
1429
\rightarrow
1382
$$

Interpreted as:

```text
32,238 all LTE-DL rows
        ↓
8,086 broad statistical candidates
        ↓
6,217 statistical RCA-eligible rows
        +
140 strict production-ML anomalies
        ↓
3,574 fused row-level handoff anomalies
        ↓
1,429 strict episodes
        ↓
1,382 operational incidents
```

The reduction is not data loss.

It is controlled consolidation:

- broad anomaly candidates are filtered by mechanism and confidence;
- overlapping statistics are grouped;
- weak isolated rows are removed;
- continuous rows are grouped into episodes;
- nearby compatible episodes become incidents.

---

# 44. Why direct score averaging is not used

A naive average would be:

$$
S_{\text{naive}}
=
\frac{
S_{\text{stat}}+S_{\text{ML}}
}{2}
$$

This creates several problems:

1. a missing ML score can suppress a strong statistical anomaly;
2. correlated models can inflate the result;
3. severity and confidence become mixed;
4. different anomaly mechanisms become compared using incompatible references;
5. radio-limited planning cases may be weakened because ML expects different behavior.

The final design instead uses:

$$
\text{Mechanism-aware impact}
+
\text{bounded independent-evidence confidence}
$$

and then:

$$
Priority
=
0.55Impact
+
0.45Confidence
$$

at every aggregation level.

---

# 45. Why radio-limited anomalies remain important

Radio-limited degradation can indicate:

- coverage weakness;
- poor dominance;
- interference;
- antenna or tilt issues;
- neighbor-planning problems;
- mobility or handover problems.

The final row impact for radio-limited cases deliberately avoids comparing poor-radio samples with an unrelated very high capability prediction.

Instead:

$$
I_{\text{radio}}
=
0.70S_{\text{low}}
+
0.30S_{\text{persistence proxy}}
$$

This keeps radio-limited incidents important without overstating their gap using an inappropriate expected reference.

---

# 46. Why LSTM and Isolation Forest do not enter final fusion

## LSTM

The LSTM held-out performance was:

$$
R^2=0.749
$$

$$
MAE=14.74\text{ Mbps}
$$

This is materially weaker than the HGB temporal model:

$$
R^2=0.920
$$

$$
MAE=8.50\text{ Mbps}
$$

The LSTM remains useful as an independent sequence-learning validation comparator, but it does not improve the production fusion enough to justify becoming an extra evidence family.

---

## Isolation Forest

Isolation Forest identifies multivariate outliers, but it does not directly predict expected throughput.

Actual result:

- 1,000 raw outliers;
- 141 context-confirmed underperformance rows.

It is retained as context validation only.

This prevents an unsupervised rarity score from being interpreted as a confirmed throughput anomaly.

---

# 47. Q75 calibration evidence

Overall Q75 held-out coverage was approximately:

$$
P(T_{\text{actual}}\le \hat{T}_{Q75})
=
0.781
$$

for the representative held-out test plot, while OOF operational deciles were close to the 0.75 target.

For operationally eligible deciles with median prediction at least 25 Mbps, coverage ranged approximately from:

$$
0.721
\text{ to }
0.765
$$

No operational decile exceeded the configured five-percentage-point warning limit.

Therefore, Q75 is suitable as an achievable-opportunity reference rather than a central expected value.

---

# 48. How to explain the complete fusion in one minute

> The pipeline starts with interpretable statistical detectors. Correlated low-throughput methods such as P10, IQR, and MAD remain visible, but they count as one low-level family. The statistical score uses a strongest-trigger floor, continuous ratio/gap/low/drop magnitude, and only small capped bonuses.
>
> Separately, three production ML models estimate expected throughput using session-safe out-of-fold predictions. Model evidence combines ratio severity, expected gap, and residual-tail extremeness. The resource and temporal model families are fused by noisy-OR.
>
> Statistical and ML evidence then create a bounded confidence score, while a mechanism-specific expected reference creates the impact score. Row priority is 55% impact and 45% confidence.
>
> One-second rows are grouped into episodes. Episode priority adds average behavior and persistence. Nearby compatible episodes are consolidated into operational incidents, where recurrence and total anomalous time are included.
>
> RCA receives the final operational incident priority, not the peak one-second score, because the incident score represents the complete engineer-facing network problem.

---

# 49. Key final messages for the presentation

1. **Statistics remain primary.**  
   96.08% of final fused rows were statistical-only.

2. **ML is strict and selective.**  
   Only 140 of 32,238 rows became final production-ML anomalies.

3. **ML-only anomalies are rare and supervised.**  
   Only 4 rows, equal to 0.012%, were retained without statistical handoff support.

4. **Impact and confidence are separate.**  
   The system does not confuse a severe anomaly with a well-supported anomaly.

5. **Bonuses cannot dominate.**  
   Median continuous magnitude was 55.80, while median context bonus was only 4.

6. **Aggregation changes the meaning of priority.**  
   Row priority represents peak instantaneous severity; incident priority represents operational investigation importance.

7. **RCA receives one canonical score.**  
   `incident_final_priority_0_100` is the final handoff and ranking field.

8. **The handoff is internally validated.**  
   JSON, CSV, and operational incident IDs and priorities match exactly across 1,382 incidents.

---

# 50. Output files supporting the presentation

The equations and numbers in this document come from the final notebook logic and these simulation outputs:

```text
anomaly_method_summary.csv
statistical_threshold_calibration_report.csv
statistical_low_tail_method_overlap.csv
fusion_component_empirical_validation.csv
fusion_evidence_ceiling_sensitivity.csv
ml_oof_fold_evaluation_report.csv
ml_train_heldout_sequence_fit_metrics.csv
ml_q75_operational_decile_validation.csv
ml_anomaly_method_summary.csv
ml_only_handoff_policy.csv
lte_throughput_anomalies_final_fused_row_level.csv
lte_throughput_anomalies_final_fused_episode_rows.csv
lte_throughput_anomaly_episodes_final_rca_handoff.csv
lte_throughput_operational_incidents_final_rca_handoff.csv
rca_anomaly_incidents_full_compact.csv
rca_anomaly_incidents_full_compact.json
final_run_metadata.json
```

The final simulation metadata records:

```text
Run timestamp: 2026-07-28T00:15:21Z
LTE-DL rows: 32,238
Final fused rows: 3,574
Final episodes: 1,429
Operational incidents: 1,382
Diverse shortlist: 15
Canonical RCA priority: incident_final_priority_0_100
```

---

# 51. Final fusion summary equation

The full system can be summarized conceptually as:

$$
\boxed{
\begin{aligned}
S_{\text{stat}}
&=
f_{\text{stat}}
(
\text{level},
\text{ratio},
\text{gap},
\text{drop},
\text{RB efficiency},
\text{family agreement}
)
\\[4pt]
S_{\text{ML}}
&=
f_{\text{ML}}
(
\text{OOF residual},
\text{ratio},
\text{gap},
\text{resource evidence},
\text{temporal evidence}
)
\\[4pt]
Priority_{\text{row}}
&=
0.55I_{\text{row}}
+
0.45C_{\text{row}}
\\[4pt]
Priority_{\text{episode}}
&=
0.55I_{\text{episode}}
+
0.45C_{\text{episode}}
\\[4pt]
Priority_{\text{incident}}
&=
0.55I_{\text{incident}}
+
0.45C_{\text{incident}}
\end{aligned}
}
$$

The final value handed to RCA is:

$$
\boxed{
Priority_{\text{RCA}}
=
Priority_{\text{incident}}
=
\texttt{incident\_final\_priority\_0\_100}
}
$$
