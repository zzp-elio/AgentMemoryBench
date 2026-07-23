"""Mem0 memory-benchmarks 作者校准 answer/judge 配置资产。"""

from __future__ import annotations

from dataclasses import dataclass

from memory_benchmark.evaluators.beam_rubric_judge import BeamRubricJudgeEvaluator
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator

MEM0_LOCOMO_NATIVE_ANSWER_PROMPT = ('You are answering a question using retrieved memories from past conversations. '
 'Follow these reasoning steps IN ORDER.\n'
 '\n'
 '## Step 1: SCAN ALL MEMORIES\n'
 'Read EVERY memory below from first to last. For each one that contains information '
 'relevant to the question, note it. Do NOT stop after finding the first relevant '
 'memory — important details are often scattered across many memories, including ones '
 'far down the list. Give equal weight to ALL memories regardless of position — a '
 'memory near the end is just as likely to contain the answer as one near the '
 'beginning. In these memories, "User" refers to the main person whose memories these '
 'are.\n'
 '\n'
 '## Step 2: ENTITY VERIFICATION\n'
 'Confirm each relevant memory is about the correct person/entity. If the question '
 'asks "What does Person A like?" and a memory says "Person B likes X", do NOT use '
 "that memory to answer about Person A. In two-person conversations, both speakers' "
 'actions are relevant — if the question asks about person A and a memory attributes '
 'an action to person B (the other speaker), that information is still valid evidence '
 'from their shared conversations, but always check the attribution is correct.\n'
 '\n'
 '## Step 3: COMBINE AND CROSS-REFERENCE\n'
 '- COMBINE facts from multiple memories about the same topic. If one memory says "won '
 'first place" and another says "performed a piece titled X," those describe the same '
 'event — connect them.\n'
 '- For listing/counting questions, extract EVERY distinct item from ALL memories. A '
 'single memory may contain multiple items. Think about what CATEGORIES of answers the '
 'question could have, then re-scan specifically for each category.\n'
 '- For counting questions ("how many times", "how many X"), enumerate each distinct '
 'instance explicitly with its date or context BEFORE giving a final count. Do not '
 'estimate — list them out, then count the list.\n'
 '- DECOMPOSE complex sentences: "an immersive X with Y, enjoys Z" contains multiple '
 'distinct facts. Each could be the answer.\n'
 '- Connect related facts across memories: if one says "nearby lake" and another says '
 '"Lake Tahoe is great for kayaking", the nearby lake IS Lake Tahoe. If one says '
 '"bought X in Paris", infer the country is France.\n'
 '\n'
 '## Step 4: SELECT THE BEST ANSWER\n'
 '- Do NOT assume the highest-ranked memory is correct. Multiple memories may describe '
 "different events for the same topic. Compare each candidate's relevance to the "
 'SPECIFIC question, not its retrieval score. A lower-ranked memory that directly '
 'answers the question beats a higher-ranked one that is only tangentially related.\n'
 '- ALWAYS choose the MOST SPECIFIC detail available. A proper name, title, or number '
 'beats a generic description. Rate each candidate as HIGH specificity (name, title, '
 'number, specific activity) or LOW (generic description), and prefer HIGH.\n'
 '- Report what someone actually DID, not what was offered or available to them. "Has '
 'not tried X yet" means X was NOT done — disqualify it. "Joined X" or "has done X" '
 'means it WAS done — prefer it.\n'
 '- When multiple memories repeat the same generic fact, that repetition does NOT make '
 'it more correct than a single memory with a more specific answer.\n'
 "- Photos depict what was IN the photo, not facts about someone's daily life. Prefer "
 'direct statements over photo descriptions for inferences.\n'
 '- Re-read the question carefully before answering. If it asks "what '
 'aspect/type/kind", answer with the specific aspect. If it asks "what did they '
 'discover they both enjoy", answer with the specific thing, not the setting.\n'
 '\n'
 '## Step 5: TEMPORAL GROUNDING\n'
 'These conversations took place around {reference_date}. All events occurred in '
 '2022-2024.\n'
 '- Calculate time relative to this date, NOT today. Never output 2025 or 2026.\n'
 '- Use dates explicitly stated in memory text. Do not invent or estimate dates.\n'
 '- When a question asks what someone "shared" or "mentioned" on a date, that date is '
 'when they TALKED about it — look for events shortly BEFORE that date.\n'
 '- For "how long" questions, find the start and end dates explicitly, then compute '
 'the duration. Do not guess.\n'
 '- TEMPORAL DISAMBIGUATION: When you find MULTIPLE instances of similar events at '
 'different dates, enumerate them all with their dates before picking. If the question '
 'uses past tense + "the" → select the instance closest to (and before) the reference '
 'date. If future tense ("plans to", "going to") → select the earliest planned date. '
 'NEVER default to the first-mentioned or highest-scored instance — the DATE '
 'determines the answer.\n'
 '\n'
 '## Step 6: INCLUSION CHECK (for lists and counts)\n'
 "If you found items during reasoning that you're tempted to exclude from your answer "
 '— STOP. Include them unless you have STRONG evidence they are wrong. The most common '
 'mistake is finding relevant items but then dropping them due to overly strict '
 'filtering. More items is better than fewer when there is supporting evidence.\n'
 '- For counting: after enumerating, re-verify each item. Check for duplicates (same '
 "event described differently) and ensure you haven't missed items from memories late "
 'in the list.\n'
 "- The question assumes something happened. Find WHAT happened, don't say nothing "
 'happened.\n'
 '\n'
 '## Step 7: COMMIT AND ANSWER\n'
 'Give a direct, specific answer. NEVER say "not specified", "not mentioned", "no '
 'record", or "the memories don\'t say" — if ANY memory contains relevant information, '
 'give the best answer from available evidence. No hedging, no caveats. If the '
 'question asks for a list, include ALL items found. NEVER return an empty answer when '
 'relevant memories exist.\n'
 '- NEVER generate specific names, titles, places, or dates that do not appear in any '
 'memory above. If no memory contains the specific detail the question asks for, '
 'answer with what the memories DO contain rather than guessing.\n'
 '- For open-domain/opinion questions ("Would X do Y?", "Is X considered Z?"):\n'
 '  * Follow the DIRECT causal reasoning in the memories. Do NOT construct elaborate '
 'counter-arguments.\n'
 '  * "Would X still do Y without Z?" — If memories show X does Y BECAUSE of Z, then '
 'without Z, answer "likely no."\n'
 '  * "Would X do Y again soon?" — If the most recent attempt involved a bad '
 'experience (accident, scare, trauma), answer "likely no." A recent negative '
 'experience outweighs historical positive patterns.\n'
 '  * For trait questions ("Is X considered Z?"): weigh ALL evidence including '
 'symbolic/indirect references. If there is SOME but not strong evidence, answer with '
 'a qualified degree ("somewhat") rather than flat "no."\n'
 '\n'
 '# Instructions\n'
 '\n'
 '## Misc\n'
 '\n'
 '1. Make reasonable deductions based on your memories. Memory shows store with a lot '
 'of working people -> store employs a lot of people\n'
 '2. If a memory describes something recognizable (e.g., "romantic drama about memory '
 'and relationships"), you may name it (e.g., "Eternal Sunshine of the Spotless '
 'Mind").\n'
 '3. Use domain knowledge to connect facts: a game exclusive to one platform implies '
 'ownership of that platform. An unnamed company deal can be linked to a previously '
 'expressed brand preference.\n'
 '\n'
 '{memories}\n'
 '\n'
 'Question: {question}\n'
 '\n'
 'Work through Steps 1-7, then give your final answer after "ANSWER:".\n')

MEM0_LONGMEMEVAL_NATIVE_ANSWER_PROMPT = ('You are a personal assistant with access to memories from past conversations with a '
 'user. Answer the question using information from the memories below. Be direct and '
 'concise.\n'
 '\n'
 "IMPORTANT: Today's date is {question_date}. All relative time expressions MUST be "
 'computed relative to this date.\n'
 '\n'
 'IMPORTANT: If memories indicate the user wants to avoid something, your answer must '
 'NOT contain it — not as primary, secondary, or context.\n'
 '\n'
 'IMPORTANT: If memories contain the numbers needed to compute the answer (ages to '
 'subtract, prices, dates to diff), DO the computation. NEVER abstain when the raw '
 'data exists — even scattered across different conversations.\n'
 '\n'
 'IMPORTANT: Keep your responses short. No need to go into too much detail, no need to '
 'describe things at the lowest level. You can generally describe events and ideas '
 'abstractly.\n'
 '\n'
 'IMPORTANT: Pay close attention to the EXACT entity in the question. If the question '
 'asks about a specific variant and memories only mention a DIFFERENT variant (e.g., '
 '"electric guitar" vs "acoustic guitar"), abstain — these are talking about different '
 'things!\n'
 '\n'
 'IMPORTANT: For comparison/savings questions, BOTH costs must come from USER-stated '
 'facts (or user-relayed, e.g., "my friend said"). Do NOT use assistant-provided '
 'general info. If only one side has a user-stated cost, abstain.\n'
 '\n'
 'IMPORTANT: If the query uses a specific but WRONG role/title/entity (e.g., asks '
 'about experience as a "Sales Manager" but memories say "Senior Sales Engineer"), do '
 "NOT answer as if they match — instead say you don't have the information! Always "
 'lean towards abstention in these cases! Do not mix up different role titles, they '
 "are not the same roles and you should say you don't have information.\n"
 '\n'
 'Before answering, reason step-by-step inside <mem_thinking> tags:\n'
 '- List every relevant memory; try to list all memories relevant to what the user '
 'wants to do! Eg. List memory of Payment management apps if query is about paying '
 'someone; list memory of travel management apps if query is about going somewhere.\n'
 '\n'
 "- For counting: enumerate each item with date. Apply the question's EXACT "
 'verb/qualifier strictly (e.g., "LED" = leader only, "BAKED" = completed baking only, '
 '"RAISED" = total from events user participated in (include team/event totals), '
 '"COMPLETED writing" = each distinct finished piece). Count multiple items in a '
 'single memory separately. Do a SECOND full scan of all memories after initial count '
 '— items at positions 30-200 are commonly missed. Verify each item is a completed '
 'action (past tense), not a plan ("plans to", "intends to").\n'
 '- For cross-topic computation: scan ALL memories for each needed fact independently '
 "— they're often in unrelated conversations. List: (a) what you need, (b) where each "
 'appears, (c) the computation.\n'
 '- For temporal questions: identify dates, compute intervals from {question_date}\n'
 "- CONTEXT CHECK: Before using a memory's value, verify it applies to the SAME "
 'context as the question. A wake-up time "while traveling" is NOT the same as a '
 'regular weekday wake-up time. A "general daily" schedule may conflict with a '
 '"specific weekday" schedule — always prefer the more specific memory that matches '
 "the question's context. List the context of each memory (weekday routine vs. travel "
 'vs. weekend vs. specific day) and only use values from the matching context.\n'
 '- For time-bounded counting: compute the INCLUSIVE date window first, then check '
 "EVERY item's date. Err on inclusion for ambiguous dates.\n"
 '- For "where is X": trace location chronologically through memories\n'
 '- For suggestions: list (a) what user has/does, (b) what they avoid/dislike, (c) '
 'what they want to explore. Check every suggestion against (b) before including.\n'
 '- State your conclusion\n'
 '\n'
 'The user will only see text outside the <mem_thinking> tags.\n'
 '\n'
 'Rules:\n'
 '\n'
 '1. **Always try to answer**: If the topic appears in any memory — even indirectly — '
 "answer using what you have. Don't refuse for one missing detail.\n"
 '\n'
 '2. **Most recent wins**: For conflicting values of the same fact, use the most '
 "recent memory. But: (a) memories about different people/contexts aren't conflicting; "
 '(b) for historical event dates, use the memory recorded closest to the event; (c) '
 "for current counts/scores/status, the latest value REPLACES all earlier ones — don't "
 'sum or average.\n'
 '\n'
 'Similarly, when memories give two numbers for the same metric (e.g., "has 1,250 '
 'followers" and "close to 1,300 followers") on the same date, treat the '
 'HIGHER/UPDATED value as current — "close to 1,300" means the count has grown from '
 '1,250 to approximately 1,300.\n'
 '\n'
 '3. **Time-bounded questions**: Compute the date window from {question_date}. Show '
 'date arithmetic in <mem_thinking>. Scan EVERY memory for events in range. "Last '
 'weekend" is imprecise — could mean up to 10 days ago as people sometimes mean '
 'weekend before the latest one. "Last 3 months" can include boundary days of the 4th '
 'month back.\n'
 '\n'
 '"Last month" includes the current month so far as well as the previous month. Eg. '
 '"last month" in Late May includes all of April. If the literal window yields '
 'nothing, check the immediately preceding period.\n'
 '\n'
 '4. **Temporal reference points**: "How many days ago did X when Y happened" — '
 'compute interval between X and Y, NOT between X and today.\n'
 '\n'
 '5. **Counting and ordering**: Scan ALL memories first to last. Build a numbered list '
 'in <mem_thinking> with date and position. Deduplicate by matching '
 'dates/descriptions. Count items in a single memory separately.\n'
 'Any addition to a list on the same day as a stated count is already included in the '
 'count\n'
 '\n'
 'When asked to count all instances of an event *before* a specific one, obviously '
 'don\'t include the specific one in the count. Eg. "how many restaurants did i visit '
 'before eating at Pizza Hut?". Obviously don\'t include Pizza Hut in the count\n'
 '\n'
 "6. **Use only the memories**: Don't invent numbers, prices, or addresses.\n"
 '\n'
 '7. **When to abstain**: Say "The information provided is not enough" when:\n'
 '   - The topic is genuinely unmentioned\n'
 '\n'
 "- The question asks about a specific event that doesn't exist, even if a related "
 'topic does\n'
 '\n'
 '- IMPORTANT: If the query uses a specific but WRONG role/title/entity (e.g., asks '
 'about experience as a "Sales Manager" but memories say "Senior Sales Engineer"), do '
 "NOT answer as if they match — instead say you don't have the information! Always "
 'lean towards abstention in these cases! Do not mix up different role titles, they '
 "are not the same roles and you should say you don't have information.\n"
 '\n'
 '   - For comparison/ordering, BOTH items must be present as completed events\n'
 '   If query asks to compare timings of two tasks and one of them did not even '
 'happen, abstain.\n'
 "   Before abstaining, do a keyword scan of ALL memories (they're chronological, not "
 'relevance-sorted — check positions 1-200). Only abstain if NO keywords match.\n'
 "   EXCEPTIONS: For suggestion questions, don't abstain for lack of real-time info — "
 'recommend based on known preferences. If you lack exact brand but have the store, '
 'output the store.\n'
 '\n'
 '8. **Yes/no and comparison**: "Did I ever do X?" with no matching memory = "No." For '
 'comparisons, find both values across all memories and compare directly.\n'
 '\n'
 '9. **Actions vs intentions**: Use the date of actual execution, not the plan date. '
 '"Decided to" or "took X for servicing" = action initiated. Only treat as plan if '
 'explicit future-tense ("plans to", "will"). A plan with a specified date and no '
 'update = assume completed on that date. If a later memory confirms execution, use '
 'the execution date — it supersedes the earlier plan.\n'
 '\n'
 'When a query asks: "when I decided to do X", it means they are asking when X was '
 'actually done.\n'
 '\n'
 '10. **User facts vs assistant advice**: "User..." = actual experience. '
 '"Assistant..." = advice. Prefer user-stated facts for personal questions. Don\'t '
 'convert currencies unless user stated the conversion.\n'
 '\n'
 '11. **Connect memories across topics**: Facts needed for computation are often in '
 "unrelated conversations (age in travel advice + relative's age in birthday "
 'discussion; cashback rate in membership talk + purchase amount in expense tracking). '
 'Search ALL memories for each fact independently.\n'
 '\n'
 '12. **Personalization**: For suggestions/recommendations:\n'
 '   - Prioritize personal preferences over informational content\n'
 "   - Apply known preferences to new contexts — don't abstain for unfamiliar "
 'destinations\n'
 '   - Acknowledge prior work before suggesting next steps\n'
 '   - Respect anti-preferences — check every suggestion against known dislikes\n'
 '   - Reference existing tools owned, not to acquire\n'
 "   - Lead with personalization, don't pad with generic alternatives\n"
 '   - Suggest similar things to the user as their habits. Eg. Logging basketball '
 'scores in a app they do usually. Eg. Adding travel logs to a travel logging app they '
 'use usually.\n'
 '   - IMPORTANT: Scan ALL top memories for user-owned tools, apps, and resources '
 'relevant to the question. If the user has a travel card (Suica), a trip organizer '
 'app (TripIt), a budgeting tool, etc., mention ALL of them — not just the most '
 'obvious one. Do a SECOND pass of the top 30 memories specifically looking for apps, '
 'tools, and resources the user has mentioned owning or using.\n'
 '\n'
 '13. **Reasonable deduction**:\n'
 '- Infer from patterns\n'
 'IMPORTANT: Assume that similar items referenced in the same sentence have the same '
 'type.\n'
 'Eg. "User ate lunch, which was the third meal with this chicken fajitas". This means '
 'the other meals with these chicken fajitas were lunch meals too, should be treated '
 'as explicit lunches.\n'
 '\n'
 '14. IMPORTANT: If two pieces of memory directly contradict each other (not just an '
 'update, a direct contradiction), then assume that the memory that was created later '
 'is true. Doesn\'t matter if a different one "appears" more reliable. If on the same '
 'day, trust the one at a later time.\n'
 '\n'
 '- Chronological actions:\n'
 'If the user is watching the 11th episode of a series is watching it normally, assume '
 'they have completed the earlier 10 too.\n'
 '\n'
 '- If you lack a name but have a description, answer with the description.\n'
 '\n'
 '**Memory grouping rules**: Memories under the same date heading are from the same '
 'conversation.\n'
 '- A count + "added X items" on the SAME date = count already includes them\n'
 '- "Aims to beat X" = X is the current value\n'
 '- "Previous" = the value superseded by a more recent one\n'
 '- Events described as just completed ("attended", "went to", "just got back from", '
 '"completed") = happened on/near that date. Undated actions = assume the event '
 "happened on the memory's date.\n"
 '\n'
 '# Misc Rules\n'
 "- Count class projects too when asked about users' projects. Class projects = "
 'projects.\n'
 '- Most old (Eg. ancestral, vintage, heritage) items count as antiques too!\n'
 "- If you don't have chords for a song (but have notes), output the notes. Song notes "
 'count as chord progressions.\n'
 '- Starting a *diorama project* (eg. diorama work, working on terrain) EXPLICITLY '
 'COUNTS AS working on that model kit; these are equivalent! Always count such items.\n'
 '- Running into someone at a coffee shop and exchanging numbers DOES NOT count as '
 'meeting them; lunch meetings do count.\n'
 "- Potlucks/feasts/birthday parties count as dinner parties (BBQ doesn't).\n"
 '- chandelier counts as jewelry\n'
 '- Always assume birthdays cleanly follow years. Ie. User was 22 in 2022; they will '
 'be 23 in 2023.\n'
 '- "scratch grains" count as "new layer feed", always include them when interpreting '
 '"new layer feed"\n'
 '\n'
 'Memories (sorted newest-first, grouped by date):\n'
 '{memories}\n'
 '\n'
 "Today's Date: {question_date}\n"
 'Question: {question}\n'
 '\n'
 'IMPORTANT: You MUST provide your full thinking in <mem_thinking> tags BEFORE giving '
 'your answer.; Reasoning and answer:')

MEM0_BEAM_NATIVE_ANSWER_PROMPT = ('You are an AI assistant with access to stored memories from prior conversations with '
 'a user.\n'
 'Use these memories to answer the following question as accurately and completely as '
 'possible.\n'
 '\n'
 'IMPORTANT RULES:\n'
 '1. Scan ALL provided memories before answering — do not stop after the first '
 'relevant one.\n'
 '2. If multiple memories contain relevant information, combine and cross-reference '
 'them.\n'
 '3. If the memories contain contradictory information, prefer the more recent one.\n'
 '4. If the memories don\'t contain enough information to answer, say exactly: "I '
 'don\'t have enough information to answer this question."\n'
 '5. For temporal questions: pay attention to dates and relative time references.\n'
 '6. For ordering questions: present events in chronological order.\n'
 '7. For preference questions: use the most recently stated preference.\n'
 '8. Be specific and direct — include exact names, dates, numbers, and details from '
 'the memories.\n'
 "9. Do NOT invent or assume information that isn't in the memories.\n"
 '\n'
 'QUESTION: {question}\n'
 '\n'
 'RETRIEVED MEMORIES:\n'
 '{memories}\n'
 '\n'
 'ANSWER:')

MEM0_LOCOMO_NATIVE_JUDGE_PROMPT = ('Label the generated answer as CORRECT or WRONG.\n'
 '\n'
 '## Rules\n'
 '\n'
 '1. **PARTIAL CREDIT**: If the generated answer includes AT LEAST ONE correct item '
 "from the gold answer's list, mark CORRECT. Getting 1 out of 2, 2 out of 4, etc. is "
 'always acceptable. Only mark WRONG if NONE of the gold answer items appear.\n'
 '\n'
 '2. **PARAPHRASES COUNT**: Same concept in different words is CORRECT. "Chocolate '
 'raspberry tart" = "chocolate cake with raspberries". "Shelter meal service" = '
 '"volunteering at a homeless shelter". Emotions and sentiments in the same '
 'positive/negative family count as paraphrases: "proud" = "fulfilled" = '
 '"accomplished"; "huge success" = "relieved" = "thrilled" (all express positive '
 'achievement). Judge semantic meaning, not exact wording.\n'
 '\n'
 "3. **EXTRA DETAIL IS FINE**: A longer answer that includes the gold answer's key "
 'facts plus additional information is CORRECT. Never penalize for being more detailed '
 'or specific. If the generated answer adds extra descriptive details beyond the gold '
 'answer while still referencing the same core entity or concept, mark CORRECT.\n'
 '\n'
 '4. **DATE TOLERANCE**: Dates within 14 days of each other are CORRECT. Durations '
 'within 50% are CORRECT (e.g., "5 months" matches "six months"; "19 days" matches '
 '"two weeks"). Relative dates ("few days before November") match specific dates in '
 'the same window. A specific date (e.g., "February 2020") that is consistent with a '
 'vague reference (e.g., "a few years ago" relative to 2023) is CORRECT. Converting '
 '"last year" to the actual year (e.g., "2022" when conversations are in 2023) is '
 'CORRECT.\n'
 '\n'
 '5. **SEMANTIC OVERLAP**: Judge whether the generated answer addresses the same topic '
 'and captures the core idea of the gold answer. Different wording, phrasing, or level '
 'of detail should not result in WRONG if the underlying concept matches. For EMOTIONS '
 'and FEELINGS questions, answers expressing sentiments in the same valence '
 '(positive/negative) about the same event are CORRECT — do not require the exact same '
 'emotion word.\n'
 '\n'
 '6. **SAME REFERENT**: If the generated answer mentions or references the same named '
 'entity, character, person, or concept as the gold answer, mark CORRECT — even if the '
 'generated answer provides a different physical description or includes additional '
 'details. The key question is: does the generated answer identify the same core '
 'entity? If yes, it is CORRECT.\n'
 '\n'
 '7. **FOCUS ON KNOWLEDGE, NOT WORDING**: The goal is to assess whether the system '
 'recalled the right fact. Minor differences in specificity, phrasing, or scope should '
 'not result in WRONG. Only mark WRONG when the generated answer demonstrates a '
 'genuinely different or incorrect understanding.\n'
 '\n'
 '## ONLY mark WRONG if:\n'
 '- The generated answer contains ZERO correct items from the gold answer\n'
 '- The answer addresses a completely different topic\n'
 '\n'
 '## Question\n'
 'Question: {question}\n'
 'Gold answer: {answer}\n'
 'Generated answer: {response}\n'
 '\n'
 'Return JSON with "reasoning" (one sentence) and "label" (CORRECT or WRONG). Do NOT '
 'include both labels.')

MEM0_LONGMEMEVAL_NATIVE_JUDGE_PROMPT = ('I will give you a question, a correct answer (or rubric), and a model response. '
 'Decide whether the model response is correct.\n'
 '\n'
 'CORE PRINCIPLE — Semantic equivalence: Judge by MEANING, not exact words. Answer '
 '"yes" if every concept in the correct answer is addressed in the response, even with '
 'different vocabulary, more specific terms, or restructured phrasing.\n'
 '\n'
 'IMPORTANT BIAS CHECK: You have a tendency to say "no" too quickly. Before concluding '
 '"no", you MUST verify the answer is truly wrong, not just differently worded. When '
 'in doubt, lean toward "yes".\n'
 '\n'
 'Rules:\n'
 '\n'
 '**Equivalence & Supersets**\n'
 '- Equivalent or superset responses are correct. Extra details are fine unless proven '
 'to be factually wrong. Extra qualifiers are fine unless proven to be wrong. E.g., "a '
 'blue dress and a matching necklace" is correct when the answer is "a blue dress."\n'
 '- If a response captures the most specific part (exact item/place/name) but omits a '
 "broader container, it's correct.\n"
 '- Same factual meaning with different phrasing = correct (e.g., "No, you did not '
 'visit with a friend" ≈ "You didn\'t mention going with anyone").\n'
 '- Adding scope qualifiers like "regular-season" or "excluding X" is fine as long as '
 'the core value is correct. The qualifier may narrow the context but does NOT make '
 'the answer wrong unless the correct answer explicitly includes the excluded items.\n'
 '\n'
 '**Lists & Compound Terms**\n'
 '- For list answers, match each item by semantic meaning. A concept is covered if '
 'restated via synonyms, sub-concepts, or related terms. Adding methodological detail '
 'or rewording verbs to near-synonyms is acceptable.\n'
 '- A broad term like "A and B significance" is covered if the response addresses the '
 'topic area through related specific terms, even without naming each component '
 'literally.\n'
 '- If some items as listed as "or"s, "maybe"s and potential answers, it\'s okay if '
 'the answer does not include those.\n'
 '- If two items in a list achieve the same purpose, listing just one of them is '
 'fine.\n'
 '\n'
 'IMPORTANT: The "anti-preference" items are very specific!\n'
 'Eg. Someone "not interested in general AI topics" could be very interested in '
 'specific AI topics in general AI *conferences*; those are not the same thing and '
 'should be accepted! topics != conferences\n'
 '\n'
 '**Numbers & Precision**\n'
 '- Hedging ("at least 3", "approximately") is fine if the core number matches. A '
 'range that includes the correct answer is correct.\n'
 'Generally, if the user themself would be satisfied by the response, it is '
 'acceptable. Ie. If the answer is conditional on information they would have (eg. '
 'their birthday, some hidden dependent information), and would be correct with that '
 'information, that is acceptable.\n'
 '- More precise answers are correct: "22 days" matches "3 weeks"; "over $270" matches '
 '"$270."; "9 1/2 months" matches "9 months";\n'
 '\n'
 '- Rough answers are correct: "about nine months" ≈ "9 months; "8 months and 20 days" '
 'matches "9 months";\n'
 '\n'
 '- Off-by-one errors on days/weeks/months are acceptable.\n'
 '- Approximate unit conversions are equivalent: "14 weeks" ≈ "3 months", "6 months" ≈ '
 '"half a year."\n'
 '- Round time ranges generously: 7 months and 16 days ≈ 8 months.\n'
 '- Notes instead of chords are acceptable when justified\n'
 '- A correct number with added context (e.g., "about 5 months ago (around December '
 '2022)") is correct — the parenthetical date is supplementary, not a contradiction.\n'
 '\n'
 '**Dates & Temporal**\n'
 '- Date format variations are equivalent: "February 1st" = "Feb 1, 2023" = "on '
 'February 1."\n'
 '- Same-day event ordering swaps are acceptable.\n'
 '- Outdated info alongside the correct updated answer is acceptable if the current '
 'value is identified.\n'
 '- "recent" is upto 6 years ago, which means 2017+\n'
 '- References like "last weekend", "last Wednesday", etc. are imprecise - people '
 "sometimes mean the weekend/Wednesday before the latest one if they're near it. "
 '"Last 3 months" can include boundary days of the 4th month back. "Last month" '
 'includes the current month so far. Be flexible with such timestamps\n'
 '\n'
 '**Counting Edge Cases**\n'
 '- If correct answer is "0" or "nothing found," model saying "not enough information" '
 'is also correct.\n'
 '- Similarly, If correct answer is "not enough information", model saying "0" or '
 '"nothing found," is also correct.\n'
 '\n'
 '**Preference/Personalization Rubrics** (apply in order):\n'
 "1. Correct if the response demonstrates awareness of user's personal context "
 '(preferences, habits, interests). Need not satisfy every rubric point.\n'
 '2. Primary criterion: do main suggestions align with what the user WANTS?\n'
 '3. Anti-preferences: evaluate the OVERALL thrust, not keyword scanning. If the '
 'response largely suggests correct options, minor incidental references to '
 '"not-preferred" things are fine.\n'
 '4. Mentioning a phone app as a MEANS to a preferred activity (e.g., meditation app '
 'for sleep) is not "suggesting phone use." Judge by the activity, not delivery '
 'mechanism.\n'
 '5. "May not prefer" = mild preference, not hard prohibition. '
 'Secondary/context-dependent inclusion is fine.\n'
 '6. Explicit acknowledgment of anti-preferences (e.g., "keep screens off") '
 'strengthens correctness.\n'
 '7. Context-dependent suggestions are acceptable (reading is fine on a bus even if '
 'rubric flags visual attention activities). Adjacent genres alongside preferred ones '
 'are additive, not contradictory.\n'
 '8. If the rubric mentions specific user resources/tools (e.g., "Suica card", "TripIt '
 'app"), the response is correct if it demonstrates awareness of the user\'s MAIN '
 'personal context even if it does not name every specific tool. The rubric is a '
 'guide, not a checklist.\n'
 '\n'
 '**Abstention Matching**\n'
 '- If correct answer = unanswerable/abstention, ANY phrasing that conveys "I don\'t '
 'have this information" is correct, regardless of what partial context is mentioned '
 'or omitted.\n'
 '- Saying "not enough information" while mentioning partial related context = correct '
 'abstention.\n'
 '- Saying "no record of X" or "only have plans for X, not actual dates" = correct '
 'abstention.\n'
 '- The key test: does the response REFUSE to answer the question? If yes, it matches '
 'an abstention ground truth, period.\n'
 '\n'
 'FINAL CHECK: Before answering "no," you MUST reason through these steps:\n'
 '1. What is the core factual claim or intent of the correct answer?\n'
 '2. Does the model response address that same claim, even in different words?\n'
 '3. Is the response a superset (correct answer + extra details)?\n'
 '4. For numbers: does the core number match, ignoring hedging/qualifiers?\n'
 '5. For abstentions: does the response effectively decline to answer?\n'
 'Only answer "no" if, after this analysis, a core concept is entirely unaddressed or '
 'contradicted.\n'
 '\n'
 'Question: {question}\n'
 '\n'
 'Correct Answer: {answer}\n'
 '\n'
 'Model Response: {response}\n'
 '\n'
 'Think step-by-step in <judge_thinking> tags, then give your final verdict as exactly '
 '"yes" or "no" on a new line after the closing tag.')

MEM0_BEAM_NATIVE_JUDGE_PROMPT = ('Evaluate whether the following LLM response demonstrates compliance with the '
 'specified RUBRIC CRITERION.\n'
 '\n'
 'QUESTION:\n'
 '{question}\n'
 '\n'
 'LLM RESPONSE:\n'
 '{response}\n'
 '\n'
 'RUBRIC CRITERION:\n'
 '{answer}\n'
 '\n'
 'SCORING GUIDELINES:\n'
 '\n'
 'First, determine whether the rubric criterion is a POSITIVE requirement (the '
 'response SHOULD include something) or a NEGATIVE constraint (the response SHOULD NOT '
 'include something).\n'
 '\n'
 '**For POSITIVE requirements** (response should contain, mention, or demonstrate '
 'something):\n'
 '- **1.0 (Complete Compliance)**: The required element is present, accurate, and '
 'complete. The response fully and clearly satisfies the rubric criterion.\n'
 '- **0.5 (Partial Compliance)**: The required element is partially present, has minor '
 'inaccuracies, or is incomplete. The core intent is present but not fully realized.\n'
 '- **0.0 (No Compliance)**: The required element is missing, incorrect, or the '
 'response is entirely off-topic / non-responsive.\n'
 '\n'
 '**For NEGATIVE constraints** (response should NOT contain or should avoid '
 'something):\n'
 '- **1.0 (Complete Compliance)**: The response is responsive to the question AND the '
 'prohibited element is absent.\n'
 '- **0.5 (Partial Compliance)**: The response is responsive but contains a borderline '
 'or ambiguous reference to the prohibited element.\n'
 '- **0.0 (No Compliance)**: The prohibited element is present in the response, OR the '
 'response is non-responsive (off-topic, refusal, empty).\n'
 '\n'
 '**Compound statement handling**: If the rubric criterion contains "and" or commas '
 'connecting multiple required elements:\n'
 '- All elements present and correct = 1.0\n'
 '- Some (but not all) elements present and correct = 0.5\n'
 '- No elements present or correct = 0.0\n'
 '\n'
 'EVALUATION RULES:\n'
 '1. **Semantic tolerance**: Paraphrases and synonyms are acceptable. The response '
 'does not need to use the exact same words as the rubric.\n'
 '2. **Numeric and date equivalence**: Treat equivalent representations as identical. '
 '"$68,000" = "68k" = "sixty-eight thousand dollars". "2 years" = "24 months". Prefer '
 'normalized comparison for numbers, currencies, dates, and durations.\n'
 '3. **Case / punctuation / whitespace tolerance**: Differences in capitalization, '
 'punctuation, and whitespace must be ignored when comparing content.\n'
 '4. **Hedging tolerance**: Do not penalize hedging language ("I think", "probably", '
 '"it seems"), passive voice, or verbosity if the substantive content satisfies the '
 'rubric criterion.\n'
 '5. **Style neutrality**: Do not penalize for tone, formatting, or length unless the '
 'rubric criterion specifically requires a particular format.\n'
 '6. **Responsiveness**: If the LLM response is completely off-topic or refuses to '
 'answer, score 0.0 for all criteria.\n'
 '7. **Independence**: Evaluate this criterion in isolation — do not consider other '
 'rubric items.\n'
 '8. **Specificity matters**: Vague or generic answers that could apply to any '
 'question score lower than specific, detailed answers.\n'
 '\n'
 'STEP-BY-STEP EVALUATION:\n'
 'Follow these steps in order:\n'
 '1. **Understand the Requirement**: Read the rubric criterion and classify it as a '
 'positive requirement or a negative constraint.\n'
 '2. **Parse Compound Statements**: If the criterion contains multiple '
 'sub-requirements joined by "and" or commas, identify each element separately.\n'
 '3. **Check Compliance**: Compare the LLM response against each element, applying the '
 'tolerance rules above (semantic, numeric, case, hedging).\n'
 '4. **Assign Score**: Use the appropriate scoring table (positive or negative) and '
 'compound-statement rule to determine the score.\n'
 '5. **Provide Reasoning**: Write a concise explanation referencing which elements '
 'were or were not satisfied.\n'
 '\n'
 'Return your evaluation as a JSON object with exactly two fields:\n'
 '{{"score": <0.0 or 0.5 or 1.0>, "reason": "<one concise sentence explaining your '
 'score>"}}')

MEM0_LOCOMO_NATIVE_JUDGE_SYSTEM_PROMPT = ('You are evaluating conversational AI memory recall. Return JSON only with the format '
 'requested.')

MEM0_BEAM_NATIVE_JUDGE_SYSTEM_PROMPT = ("You are an expert evaluator assessing whether an AI assistant's response satisfies "
 'specific rubric criteria. You must be objective, fair, and consistent. Return ONLY '
 'valid JSON with the exact format requested.')

@dataclass(frozen=True)
class Mem0NativeAnswerSettings:
    """Mem0 官方 harness answer 调用的静态采样参数。"""

    temperature: float
    max_tokens: int
    top_p: float | None


@dataclass(frozen=True)
class Mem0NativeAnswerProfile:
    """一个 benchmark 的 Mem0 native answer 静态 profile。"""

    profile_name: str
    prompt_template: str
    settings: Mem0NativeAnswerSettings
    official_source: str


@dataclass(frozen=True)
class Mem0NativeJudgeProfile:
    """一个 benchmark 的 Mem0 native judge 静态 profile。"""

    profile_name: str
    prompt_template: str
    system_prompt: str
    evaluator_type: type
    temperature: float
    max_tokens: int
    n: int
    response_format: dict[str, str] | None
    skipped_categories: frozenset[str]
    official_source: str


MEM0_NATIVE_ANSWER_SETTINGS = Mem0NativeAnswerSettings(
    temperature=0.0,
    max_tokens=4096,
    top_p=None,
)

MEM0_NATIVE_ANSWER_PROFILES = {
    "locomo": Mem0NativeAnswerProfile(
        profile_name="mem0_locomo_memory_benchmarks_native_v1",
        prompt_template=MEM0_LOCOMO_NATIVE_ANSWER_PROMPT,
        settings=MEM0_NATIVE_ANSWER_SETTINGS,
        official_source="memory-benchmarks/benchmarks/locomo/prompts.py:40-98,143-195; run.py:465-466",
    ),
    "longmemeval": Mem0NativeAnswerProfile(
        profile_name="mem0_longmemeval_memory_benchmarks_native_v1",
        prompt_template=MEM0_LONGMEMEVAL_NATIVE_ANSWER_PROMPT,
        settings=MEM0_NATIVE_ANSWER_SETTINGS,
        official_source="memory-benchmarks/benchmarks/longmemeval/prompts.py:37-155,210-258; run.py:587-593",
    ),
    "beam": Mem0NativeAnswerProfile(
        profile_name="mem0_beam_memory_benchmarks_native_v1",
        prompt_template=MEM0_BEAM_NATIVE_ANSWER_PROMPT,
        settings=MEM0_NATIVE_ANSWER_SETTINGS,
        official_source="memory-benchmarks/benchmarks/beam/prompts.py:29-48,104-158; run.py:738-739",
    ),
}

MEM0_NATIVE_JUDGE_PROFILES = {
    "locomo": Mem0NativeJudgeProfile(
        profile_name="mem0_locomo_memory_benchmarks_native_judge_v1",
        prompt_template=MEM0_LOCOMO_NATIVE_JUDGE_PROMPT,
        system_prompt=MEM0_LOCOMO_NATIVE_JUDGE_SYSTEM_PROMPT,
        evaluator_type=LoCoMoJudgeEvaluator,
        temperature=0.0, max_tokens=4096, n=1,
        response_format={"type": "json_object"},
        skipped_categories=frozenset({"5"}),
        official_source="memory-benchmarks/benchmarks/locomo/prompts.py:203-292; run.py:470-479,708",
    ),
    "longmemeval": Mem0NativeJudgeProfile(
        profile_name="mem0_longmemeval_memory_benchmarks_native_judge_v1",
        prompt_template=MEM0_LONGMEMEVAL_NATIVE_JUDGE_PROMPT,
        system_prompt="",
        evaluator_type=LongMemEvalJudgeEvaluator,
        temperature=0.0, max_tokens=4096, n=1,
        response_format=None,
        skipped_categories=frozenset(),
        official_source="memory-benchmarks/benchmarks/longmemeval/prompts.py:265-359; run.py:605-614",
    ),
    "beam": Mem0NativeJudgeProfile(
        profile_name="mem0_beam_memory_benchmarks_native_judge_v1",
        prompt_template=MEM0_BEAM_NATIVE_JUDGE_PROMPT,
        system_prompt=MEM0_BEAM_NATIVE_JUDGE_SYSTEM_PROMPT,
        evaluator_type=BeamRubricJudgeEvaluator,
        temperature=0.0, max_tokens=4096, n=1,
        response_format={"type": "json_object"},
        skipped_categories=frozenset(),
        official_source="memory-benchmarks/benchmarks/beam/prompts.py:163-233; run.py:555-570",
    ),
}

__all__ = [
    "MEM0_BEAM_NATIVE_ANSWER_PROMPT", "MEM0_BEAM_NATIVE_JUDGE_PROMPT",
    "MEM0_BEAM_NATIVE_JUDGE_SYSTEM_PROMPT", "MEM0_LOCOMO_NATIVE_ANSWER_PROMPT",
    "MEM0_LOCOMO_NATIVE_JUDGE_PROMPT", "MEM0_LOCOMO_NATIVE_JUDGE_SYSTEM_PROMPT",
    "MEM0_LONGMEMEVAL_NATIVE_ANSWER_PROMPT", "MEM0_LONGMEMEVAL_NATIVE_JUDGE_PROMPT",
    "MEM0_NATIVE_ANSWER_PROFILES", "MEM0_NATIVE_ANSWER_SETTINGS",
    "MEM0_NATIVE_JUDGE_PROFILES", "Mem0NativeAnswerProfile",
    "Mem0NativeAnswerSettings", "Mem0NativeJudgeProfile",
]
