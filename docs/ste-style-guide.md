# The writing standard: ASD-STE100 Simplified Technical English

Use these rules for every README and for `docs/ste-style-guide.md` in each repository. Copy this file
into the repository as `docs/ste-style-guide.md` and add a **project vocabulary** section (Section 3)
with the technical names and technical verbs of that project.

## 1. The writing rules

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, `test` is a noun or a verb, `check` is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: `prepare`, `do`, `find`, `get`, `make`.
4. Do not use an `-ing` form as a noun or an adjective (`the running job`, `after indexing`).
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write `A, B or both`.
7. Do not use `should`, `could`, `would` or `may` for instructions. Use `must` for a rule, the
   imperative for a step and `can` for a possibility.
8. Keep the articles `a`, `an` and `the` in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: `Run the tests.` Not `The tests should be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: `If the index is stale, build it again.`
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase (`The cost model`) or an imperative (`Run the demo`).
   Do not start a heading with an `-ing` form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or `check that` |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |

## 3. Project vocabulary

This section gives the technical names and the technical verbs of riverpulse. The README uses each term with only this meaning.

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **site** | One sampling point of the archive (`sample.samplingPoint.notation`) | station (for water), location |
| **visit** | All measurements of one site at one date and time | sample (alone), record |
| **determinand** | One measured property, for example `ammonia_n` | parameter, pollutant, variable (alone) |
| **measurement** | One value of one determinand at one visit | reading, observation |
| **archive** | The Environment Agency water-quality archive CSV files | database, dump |
| **tidy table** | One row for each measurement, after ingest | long table, clean data |
| **LOD** | Limit of detection. A result with qualifier `<` is below it | detection limit, censored value |
| **objective** | The screening limit of one determinand in the index | standard, threshold (alone) |
| **index** | The CCME Water Quality Index, 0 to 100, higher is better | WQI score, rating |
| **exceedance** | A measurement outside its objective | violation, breach |
| **weather station** | A fixed point with a daily weather file | site (for weather) |
| **grid cell** | The 0.1-degree cell that gives the weather of a site | pixel, tile |
| **antecedent rain** | Rain sum over the 1, 3, 7 or 14 days that end on the visit date | lagged rain, prior rainfall |
| **period** | `before`, `during` or `after` the COVID restrictions | phase, era |
| **balanced panel** | The sites with enough measurements in each period | matched sites, cohort |
| **interrupted time series** | The regression with a trend, a season and period terms | ITS model, before-after test |
| **naive phase means** | The means of all visits in each period, with no site matching | raw comparison |
| **climatology** | The training mean of one site and calendar month | seasonal baseline |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **ingest** | Read archive files into the tidy table |
| **convert** | Change a unit to mg/l, or BNG coordinates to WGS84 |
| **link** | Join the weather of a grid cell to each visit |
| **index** | Calculate the CCME index for a group of visits |
| **fit** | Calculate the regression coefficients |
| **cluster** | Group the residuals by site for the standard errors |
| **forecast** | Predict a determinand for visits after the cut-off date |
