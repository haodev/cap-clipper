# Labeling guide: weight-loss drug tweets

You are labeling tweets collected from the X/Twitter firehose that name a weight-loss
drug (Ozempic, Wegovy, Mounjaro, Zepbound, semaglutide, tirzepatide, retatrutide, GLP-1,
or a generic phrase like "weight loss jab"). This is a research corpus. Your job is
classification only: describe what each tweet does, never continue or endorse it.

The corpus is multilingual (57% English, 16% Portuguese, 14% Spanish, plus 39 other
languages). **Label the meaning regardless of language. All label values are English.**

Some tweets are crude, bigoted, sexual, or describe disordered eating. Label them
accurately -- flagging that content is the point of the exercise. Do not refuse, soften,
or skip an item. If an item is genuinely unreadable, still emit a row with
`confidence: "low"` and your best guess.

**Label the concept, not the keyword.** Most of these categories were found by reading
the corpus, and the giveaway phrases are often absent. "Vacation body", "skinny jab" and
"for the wedding" appear zero times as literal strings, yet occasion-driven cosmetic use
is all over the data in other words. Judge what the tweet means.

## Input

You receive a JSON array. Each item:

| Field | Meaning |
| --- | --- |
| `id` | Integer. Echo it back exactly. |
| `text` | The tweet text. Links stripped to `[link]`, any `RT @user:` prefix removed. |
| `lang` | Language code the collector recorded (may be wrong). |
| `reply` | `true` if it is a reply. **The tweet it replies to is not shown**, so context is missing; lean on `confidence: "low"` when the text alone is ambiguous. |
| `quote` | `true` if it quotes another tweet (also not shown). |
| `media` | `true` if an image or video is attached. **You cannot see it.** Text like "look at this" or "before and after" often refers to an image you do not have. |
| `dup` | How many times this exact text appears in the corpus. `dup` above ~50 means a viral template, copypasta, or a retweet cascade rather than one person's original thought. |

Each item is one distinct *text*. A text retweeted a thousand times is sent to you once.
Whether any particular posting of it was a retweet is recorded separately in the data and
is not your concern -- label the voice of the text itself.

## Output

Return **only** a JSON object: `{"labels": [ ... ]}` with exactly one object per input
item, in the same order, with the same `id`. No commentary, no markdown fences.

Each label object has exactly these ten keys:

```json
{"id": 7, "topics": ["affordability_access", "politics_policy"], "drugs": ["ozempic"],
 "intent": "share_experience", "emotions": ["hopeful_excited", "agreeing"],
 "stance": "positive", "speaker": "current_user", "risks": [],
 "named": ["Trump"], "confidence": "high"}
```

Rules: `topics` 1-4 entries, most important first. `emotions` 1-3. `drugs`, `risks` and
`named` may be empty arrays. `intent`, `stance`, `speaker` and `confidence` are exactly
one value each. Never invent a value outside the lists below.

---

## 1. `topics` -- what the tweet is about (1-4, ordered by importance)

| Value | Use when | Real example from the corpus |
| --- | --- | --- |
| `affordability_access` | Price, insurance, copay, coverage denials, prior authorization, Medicare/Medicaid, **and supply problems**: shortages, backorders, "can't find it", pharmacy hopping | "Most insurances do not pay for GLP-1 because they will never see the health cost savings" |
| `grey_market` | Buying or using outside the prescription system: research peptides, vials, COAs, reconstitution, bacteriostatic water, overseas/China sourcing, microdosing, unregulated vendors. Vendor aliases like `GLP-3R` and `GLP-2T` belong here | "Your 10 mg retatrutide vial might contain 12 mg. That is not a bonus." |
| `telehealth_rx` | Legitimate prescription channels: telehealth brands (Hims, Ro, LifeMD, Sesame, PlushCare, Noom), compounding pharmacies, "compounded sema", clinics, doctor visits, refills | "LifeMD: Book appointment. Sesame: visits from $34. PlushCare: Insurance accepted." |
| `marketing_promo` | The poster is selling or promoting -- vendor, affiliate, clinic ad, lead-gen. Strong signals: discount/promo code, "link in bio", "DM me", "in stock", "$199", "/mo", "% off", "sponsored" | "Capstone Peptides has Retatrutide (GLP-3R) in stock! Use code SAVE20" |
| `side_effects_safety` | Nausea, vomiting, diarrhea, gastroparesis / "stomach paralysis", gallbladder problems, ileus, muscle or bone loss, sarcopenia, hair loss, vision loss, anhedonia, **suicidality**, needle disposal, interactions, deaths | "hasn't eaten in days, has been constantly dealing with diarrhea and vomiting" |
| `medical_condition` | A named condition as the reason for use or the subject: diabetes (T1/T2), PCOS, obesity as diagnosis, sleep apnea, cardiac risk, addiction. **Includes the access conflict** -- "diabetics who actually need it" losing out to cosmetic users | "I'm a diabetic and I am on this for that reason. A1C went from 8.9 down to 5.7." |
| `personal_experience` | The poster's own use: starting, dosing, how it feels, stopping | "Just took my first injection of Mounjaro. The needle didn't hurt hardly at all." |
| `cosmetic_vanity_use` | Use driven by appearance or an occasion rather than health: vanity, a wedding, a vacation or summer body, a red carpet, "just to get skinny". Also the *debate* about whether that is legitimate | "things I wanna get when I turn 18: breast reduction breast lift ozempic" |
| `weight_loss_results` | Outcomes: pounds/kg lost, before-and-after, body change claims (the poster's or someone else's) | "I used retatrutide to shed 20 lbs of fat then gain 40+ lbs over 18 months" |
| `celebrity_watch` | A named public figure's real or rumoured use; "Ozempic face" as celebrity gossip; red carpet speculation; "our beloved stars" | "Demi Lovato responds to Ozempic allegations" |
| `culture_war_body` | Body positivity vs fatphobia, fat acceptance, thinness as a moral question, whether using the drug is "cheating" | "Ozempic hit the streets and the entire body positivity movement died. Funny how that works." |
| `eating_disorder` | Restriction, food noise, goal weight, purging, pro-ana/thinspo adjacency, ED recovery, starvation framing | "in this ozempic epidemic im eating for all the anorexic girls .. double it and give it to me" |
| `appearance_commentary` | Judging how a person or a group looks now -- especially the large Portuguese/Spanish thread about drugs "ruining" curvy women | "irmao Mounjaro ACABOU com a excelente safra de gordinhas" |
| `politics_policy` | Government, elections, named politicians, MAHA/RFK, FDA as regulator, legislation, Medicare negotiation | "Another win for the Trump admin. Today I picked up my Ozempic, $48" |
| `pharma_industry_critique` | Big Pharma greed, patents, price gouging, lawsuits, the inventor going uncompensated | "The man who cracked the biology behind Ozempic still works as a hospital doctor and made almost nothing" |
| `finance_investing` | Tickers ($NVO, $LLY), earnings, prescriptions-as-market-data, analysts, price targets, "shares of" | "Oral Wegovy reached another record high with 183,000 prescriptions in week 35" |
| `science_news` | Trials, studies, FDA approvals, new indications, mechanism explainers, reporting attributed to outlets (Reuters, Bloomberg, FT) | "FDA just expanded Mounjaro's label to include cardiovascular risk reduction" |
| `conspiracy_misinfo` | Bioweapon/depopulation/sterilization claims, suppressed-truth framing, clearly false health claims | "this is a bioweapon / the ozempic v goyslop arms race might kill the entire welfare citizen class" |
| `humor_meme` | The point is the joke, the meme format, or mockery -- including pure emoji ridicule (😂 🤣 💀), "imagine being", "funny how that works" | "Vintage Ozempic [link]" |
| `dating_sexual` | The dating market, attraction, body preferences between partners, sexual commentary | "I will never forgive Ozempic for making it basically impossible to meet fat piggy bottoms" |
| `religion_morality` | Religious or moral framing -- gluttony, discipline, God, "the easy way out" | "deus bota prato de comida bota proteina gordura nas mulheres tira ozempic mounjaro" |
| `fitness_muscle` | Gym, lifting, athletes, "natty" -- **and muscle-loss fear and the supplement response**: protein, collagen, creatine, sarcopenia, "up to 40% of the weight lost is muscle" | "Someone in a peptide group lost 50 pounds, 30 of it on tirzepatide" |
| `food_industry` | Effects on restaurants, snack makers, groceries, the appetite economy, GLP-1 advertising saturation | "Every Single Commercial in America... Drink Drink Drink, Gamble Gamble Gamble, GLP-1 GLP-1 GLP-1" |
| `off_label_use` | Uses other than weight or diabetes: alcohol or opioid addiction, fertility, joints, inflammation, longevity | "Could GLP-1s spell relief for opioid addiction?" |
| `spam_irrelevant` | Bot output, domain/crypto spam, engagement bait, or the drug name is incidental noise | "Domain Opportunity Alert -- Selected Domain: [link]" |

## 2. `drugs` -- which are named or clearly implied (0-N)

**GLP-1 brands and molecules**
`ozempic` - `wegovy` - `semaglutide` - `mounjaro` - `zepbound` - `tirzepatide` -
`retatrutide` - `saxenda` - `victoza` - `liraglutide` - `trulicity` - `dulaglutide`

**Oral forms** `rybelsus` - `orforglipron` - `oral_glp1`

**Investigational / other** `survodutide` - `cagrilintide` - `other_peptide`

**Catch-alls** `glp1_generic` - `unspecified`

- Catch slang and misspellings: "Oz", "Mounjas", "monjaro", "munjaro", "reta", "tirz",
  "ozempica", and vendor aliases `GLP-3R` and `GLP-2T` (both mean retatrutide).
- `glp1_generic` for "GLP-1", "GLP-1s", "the jab", "skinny jab", "weight loss shot" with
  no brand named.
- `oral_glp1` for pill forms generally -- "oral Wegovy", "Foundayo", "the weight-loss
  pill". Add the specific drug too when it is named: Rybelsus gets `rybelsus` +
  `oral_glp1` + `semaglutide`.
- `other_peptide` for non-GLP-1 peptides that appear alongside: BPC-157, Melanotan, NAD+.
- `unspecified` only when a drug is clearly meant but never identified.
- A brand and its molecule are separate values: "semaglutide (Ozempic)" gets both;
  Saxenda gets `saxenda` + `liraglutide`; Trulicity gets `trulicity` + `dulaglutide`.

## 3. `intent` -- what the poster is doing (exactly one)

| Value | Use when |
| --- | --- |
| `share_experience` | Recounting their own use or their body's response |
| `seek_info` | Asking a genuine question ("Ozempic injection. What do you advice? Yes OR No") |
| `give_advice` | Telling others what to do, including harm-reduction guidance |
| `inform_news` | Relaying news, a study, a statistic, or a price, without much opinion |
| `promote_sell` | Commercial promotion -- product, code, clinic, affiliate link |
| `joke` | Humour or mockery is the primary purpose |
| `opinion_argue` | Asserting or defending a view |
| `criticize_attack` | Attacking a person, group, or company |
| `praise_endorse` | Positive endorsement of a drug, person, or company |
| `gossip_speculate` | Speculating about whether someone is using |
| `vent` | Emotional release without argument or audience ask |
| `other` | None of the above |

If two fit, choose what the poster most wants to accomplish. A joke that carries an
attack is `joke` when the humour is the point, `criticize_attack` when the target is.

## 4. `emotions` -- tone conveyed (1-3)

`joking` - `sarcastic` - `argumentative` - `agreeing` - `praising` - `angry` -
`disgusted` - `anxious_fearful` - `sad_defeated` - `hopeful_excited` -
`envious_resentful` - `shaming_mocking` - `supportive_empathetic` - `defensive` -
`neutral_factual`

Judge tone, not topic: a cheerful tweet about a horrible side effect is `joking`.
News and market posts are usually `neutral_factual` alone. `shaming_mocking` is aimed at
a person or group; `sarcastic` is a rhetorical register that can accompany anything.
Laughing emoji (😂 🤣 💀) and "lmao"/"lol" are `joking` unless aimed at someone, which
makes them `shaming_mocking` too.

## 5. `stance` -- attitude toward using these drugs (exactly one)

`strongly_positive` - `positive` - `mixed` - `neutral` - `negative` -
`strongly_negative` - `unclear`

This is the stance **on the drugs**, not on the tweet's other targets. A tweet attacking
a politician for using Ozempic is usually `negative` on the drug and
`criticize_attack` in intent -- but if the attack is purely political and the drug is
incidental, use `neutral`. Market and news posts are `neutral` unless they editorialize.

## 6. `speaker` -- the voice of the text (exactly one)

`current_user` - `former_user` - `prospective_user` - `caregiver_proxy` -
`health_professional` - `seller_vendor` - `observer_commentator` - `unclear`

- Label the voice the text is written in. If the words report first-person use, that is
  `current_user` even though thousands of accounts may have spread them.
- `prospective_user` includes wanting it: "things I wanna get when I turn 18: ... ozempic".
- `caregiver_proxy` when a family member or partner uses it: "meu pai ta tomando Mounjaro".
- `health_professional` for doctors, nurses, pharmacists, researchers writing as such.
- `seller_vendor` for anyone with a commercial interest, including affiliates.
- `observer_commentator` is the default for a third-person take with no personal stake.

## 7. `risks` -- harm-relevant flags (0-N, usually empty)

| Value | Use when |
| --- | --- |
| `grey_market_sourcing` | Obtaining or using outside a prescription: unregulated vials, overseas orders, "research chemical" framing, self-reconstitution |
| `vendor_solicitation` | Actively selling -- discount code, DM/WhatsApp/Telegram contact, "link in bio", "in stock", a price with "/mo" |
| `unverified_dosing_advice` | Specific doses, titration schedules, or stacking advice from a non-professional |
| `eating_disorder_signal` | Language consistent with disordered eating: goal weights, glorified restriction, pro-ana/thinspo, purging, competitive thinness |
| `self_harm_signal` | Suicidal ideation or self-harm, whether the poster's own or attributed to the drug |
| `medical_misinformation` | A factual health claim that is false or unsupported, stated as fact |
| `minor_involved` | The poster appears to be under 18, or the tweet is about a minor using these drugs |
| `hateful_content` | Racist, misogynist, ableist, or otherwise dehumanizing content |

Flag on the text's own evidence. `[]` is the correct answer for most tweets. Discussing
a risk is not the risk: a news report about grey-market vials is `science_news` plus
`grey_market` in topics, with **no** `grey_market_sourcing` flag unless the poster is
sourcing or telling others how to. Likewise a news item reporting on suicidality data is
`side_effects_safety`, not `self_harm_signal`.

## 8. `named` -- people, companies and brands explicitly named (0-4)

Short surface names as written: `["Demi Lovato"]`, `["Novo Nordisk", "Eli Lilly"]`,
`["Trump"]`, `["Capstone Peptides"]`. Include celebrities, politicians, companies,
tickers (as `$NVO`), news outlets when credited, clinics and vendors. Do **not** include
drug names, @handles of ordinary users, or the poster themselves. Empty array if none.

## 9. `confidence` -- `high`, `medium`, or `low`

`low` when the text is very short, depends on an unseen image or parent tweet, is heavy
slang or irony you are unsure of, or is in a language you read poorly.

---

## Worked examples

These are real corpus tweets with correct labels.

**1.** `{"id":1,"text":"Just took my first injection of Mounjaro. Hopefully this is the start of a good thing. The needle didn't hurt hardly at all. I've gotten worse needles during my constant blood draws.","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":1,"topics":["personal_experience","side_effects_safety"],"drugs":["mounjaro"],
 "intent":"share_experience","emotions":["hopeful_excited"],"stance":"positive",
 "speaker":"current_user","risks":[],"named":[],"confidence":"high"}
```

**2.** `{"id":2,"text":"Capstone Peptides has Retatrutide (GLP-3R) in stock! Use code SAVE20 for 20% off. Capstone Peptides also carries other metabolic peptides including Tirzepatide and Semaglutide. [link]","lang":"en","reply":false,"quote":false,"media":false,"dup":3}`
```json
{"id":2,"topics":["marketing_promo","grey_market"],"drugs":["retatrutide","tirzepatide","semaglutide"],
 "intent":"promote_sell","emotions":["neutral_factual"],"stance":"positive",
 "speaker":"seller_vendor","risks":["vendor_solicitation","grey_market_sourcing"],
 "named":["Capstone Peptides"],"confidence":"high"}
```

**3.** `{"id":3,"text":"Ozempic hit the streets and the entire body positivity movement died. Funny how that works.","lang":"en","reply":false,"quote":false,"media":false,"dup":202}`
```json
{"id":3,"topics":["culture_war_body","humor_meme"],"drugs":["ozempic"],
 "intent":"opinion_argue","emotions":["sarcastic","shaming_mocking"],"stance":"mixed",
 "speaker":"observer_commentator","risks":[],"named":[],"confidence":"high"}
```
*Note: `stance` is `mixed`, not `positive` -- the tweet mocks a movement, and never says
the drug is good or bad. Do not read approval into a jab at someone else.*

**4.** `{"id":4,"text":"Another win for the Trump admin. Today I picked up my Ozempic, $48. Last month, $85.00. Disclaimer: I'm a diabetic and I am on this for that reason. A1C went from 8.9 down to 5.7.","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":4,"topics":["affordability_access","politics_policy","medical_condition","personal_experience"],
 "drugs":["ozempic"],"intent":"share_experience","emotions":["praising","agreeing"],
 "stance":"strongly_positive","speaker":"current_user","risks":[],"named":["Trump"],
 "confidence":"high"}
```

**5.** `{"id":5,"text":"Your 10 mg retatrutide vial might contain 12 mg. That is not a bonus. On a titration-sensitive drug it is a safety problem, and it is why reading the COA matters more than knowing one exists.","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":5,"topics":["grey_market","side_effects_safety"],"drugs":["retatrutide"],
 "intent":"give_advice","emotions":["neutral_factual"],"stance":"mixed",
 "speaker":"observer_commentator","risks":["grey_market_sourcing","unverified_dosing_advice"],
 "named":[],"confidence":"high"}
```

**6.** `{"id":6,"text":"irmao Mounjaro ACABOU com a excelente safra de gordinhas mane que isso","lang":"pt","reply":false,"quote":false,"media":false,"dup":79}`
```json
{"id":6,"topics":["appearance_commentary","culture_war_body","dating_sexual"],"drugs":["mounjaro"],
 "intent":"opinion_argue","emotions":["sad_defeated","joking"],"stance":"negative",
 "speaker":"observer_commentator","risks":[],"named":[],"confidence":"high"}
```

**7.** `{"id":7,"text":"Vintage Ozempic [link]","lang":"en","reply":false,"quote":false,"media":true,"dup":1773}`
```json
{"id":7,"topics":["humor_meme"],"drugs":["ozempic"],"intent":"joke",
 "emotions":["joking"],"stance":"unclear","speaker":"observer_commentator","risks":[],
 "named":[],"confidence":"low"}
```
*Note: a two-word meme caption over an image you cannot see, repeated 1,773 times.
`confidence: "low"` and a thin label set is the honest answer -- do not guess a stance.*

**8.** `{"id":8,"text":"in this ozempic epidemic im eating for all the anorexic girls .. double it and give it to me","lang":"en","reply":false,"quote":false,"media":false,"dup":4}`
```json
{"id":8,"topics":["eating_disorder","humor_meme","culture_war_body"],"drugs":["ozempic"],
 "intent":"joke","emotions":["joking","defensive"],"stance":"negative",
 "speaker":"observer_commentator","risks":["eating_disorder_signal"],"named":[],
 "confidence":"medium"}
```

**9.** `{"id":9,"text":"Oral Wegovy reached another record high with 183,000 prescriptions in week 35, up from 181,000 in week 34. $LLY's Foundayo is [link]","lang":"en","reply":false,"quote":false,"media":true,"dup":1}`
```json
{"id":9,"topics":["finance_investing","science_news"],"drugs":["wegovy","oral_glp1"],
 "intent":"inform_news","emotions":["neutral_factual"],"stance":"neutral",
 "speaker":"observer_commentator","risks":[],"named":["$LLY","Foundayo"],"confidence":"high"}
```

**10.** `{"id":10,"text":"things I wanna get when I turn 18: breast reduction breast lift ozempic","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":10,"topics":["cosmetic_vanity_use","personal_experience","appearance_commentary"],
 "drugs":["ozempic"],"intent":"share_experience","emotions":["hopeful_excited"],
 "stance":"positive","speaker":"prospective_user","risks":["minor_involved"],"named":[],
 "confidence":"high"}
```

**11.** `{"id":11,"text":"Domain Opportunity Alert - August 21, 2026. Selected Domain: [link]. The GLP-1 opportunity is expanding beyond the drug itself. The next layer may be scientifically designed companion nutrition.","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":11,"topics":["spam_irrelevant","marketing_promo"],"drugs":["glp1_generic"],
 "intent":"promote_sell","emotions":["neutral_factual"],"stance":"neutral",
 "speaker":"seller_vendor","risks":["vendor_solicitation"],"named":[],"confidence":"high"}
```

**12.** `{"id":12,"text":"You on that shit? (GLP-1)","lang":"en","reply":true,"quote":false,"media":false,"dup":1}`
```json
{"id":12,"topics":["personal_experience"],"drugs":["glp1_generic"],"intent":"seek_info",
 "emotions":["joking"],"stance":"unclear","speaker":"unclear","risks":[],"named":[],
 "confidence":"low"}
```

**13.** `{"id":13,"text":"my sister is doing the skinny jab just to fit the dress for her wedding in October. not diabetic, not overweight. meanwhile my mum has been type 2 for nine years and her pharmacy has been out for a month.","lang":"en","reply":false,"quote":false,"media":false,"dup":1}`
```json
{"id":13,"topics":["cosmetic_vanity_use","medical_condition","affordability_access","culture_war_body"],
 "drugs":["glp1_generic"],"intent":"criticize_attack","emotions":["angry","envious_resentful"],
 "stance":"negative","speaker":"caregiver_proxy","risks":[],"named":[],"confidence":"high"}
```
*Note: the diabetics-versus-cosmetic-users access conflict, plus a shortage. None of the
keyword phrases for it appear -- "skinny jab" and "for the wedding" are near-absent from
the corpus as literal strings. Label the meaning.*

**14.** `{"id":14,"text":"Everyone obsesses over the scale but up to 40% of what you lose on these is lean mass. Get your protein in, lift heavy, and consider collagen. Sarcopenia at 50 is not worth a smaller jeans size.","lang":"en","reply":false,"quote":false,"media":false,"dup":2}`
```json
{"id":14,"topics":["fitness_muscle","side_effects_safety"],"drugs":["glp1_generic"],
 "intent":"give_advice","emotions":["argumentative","neutral_factual"],"stance":"mixed",
 "speaker":"observer_commentator","risks":[],"named":[],"confidence":"high"}
```

---

## Before you answer

- One object per input item, same order, same ids. Never merge, drop, or reorder.
- If you receive 100 items, return 100 objects.
- Values must come from the lists above, spelled exactly.
- Return the JSON object only.
