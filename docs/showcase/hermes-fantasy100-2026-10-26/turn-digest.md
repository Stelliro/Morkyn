
## T1 (10.58s, 0 calls)
  > I walk across the square to the signpost and read the notices.
  at Thornhallow | gold 12 | hp 20 | energy 16 | +15 min
  new rows: {"quests": {"rows": ["#1 skilled labor"], "writes": [26, 27, 28]}, "quest_steps": {"rows": ["#1 Seeking skilled labor! Good pay for honest work."], "writes": [29]}}
  · {"decision": "routine_read_no_check", "line": "I walk across the square to the signpost and read the notices."}
  · {"decision": "name_is_a_person", "name": "Benedict Hobb", "by": "ask", "why": "op_person"}
  · {"decision": "model_move_dropped", "destination": "[[L1]] THORNHALLOW", "why": "not_a_place"}
  · {"decision": "route_is_not_the_destination", "route": "square", "destination": ""}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: tacked to its sides: "Seeking skilled labor! Good pay for honest work." "Hedge-mage's apprentice wanted - apply within." "Lost: small wooden box, brass hasp. Reward offered." You take in the scene, making a mental note of the directions and places marked here.

## T2 (13.98s, 0 calls)
  > I ask the nearest townsfolk about the notice for skilled labor and who posted it.
  at Thornhallow | gold 12 | hp 20 | energy 16 | +5 min
  new rows: {"locations": {"rows": ["#2 The Shears and Wheel"], "writes": [11, 12]}}
  coins in prose: ['15 gold']
  die check:persuasion check failure 1d20=3
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most people are curious and would stop to ask about the notice."}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "venue_from_summary", "name": "The Shears and Wheel", "kind": "tavern", "parent": 1}
  · {"decision": "sketch_confirmed", "name": "Roger", "evidence": "ops"}
  prose end: e gestures towards the establishment. "The pay is 15 gold for a week's work, and lodging provided. Not bad for a quiet town like this. I'd suggest talking to Oriel Draper who handles hiring. She's usually in her shop, Woodall and Daughters just down the lane."

## T3 (8.69s, 0 calls)
  > I thank Roger and head to #L2 to see about the work at the tavern.
  at Thornhallow | gold 12 | hp 20 | energy 15 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A"]}
  · {"decision": "place_bound_by_reference", "code": "L2", "place": "The Shears and Wheel", "words": "The Shears and Wheel"}
  · {"decision": "noun_is_no_figure", "kind": "signpost", "by": "ask", "first": false, "check": null}
  · {"decision": "player_code_travel", "code": "L2", "destination": "The Shears and Wheel", "replaced": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "at The Shears and Wheel", "confirm": "Yes, you are"}
  prose end: ith piercing blue eyes, then quickly turns and hurries away. You arrive at the front door of The Shears and Wheel [[L2]] tavern. A carved wooden sign above the doorway shows a pair of shears cutting wheat stalks. Pushing open the heavy oaken door, you enter...

## T4 (13.46s, 0 calls)
  > I push through the door, look around the tavern and greet whoever is behind the bar.
  at Thornhallow | gold 12 | hp 20 | energy 15 | +5 min
  new rows: {"npcs": {"rows": ["#2 Arnulf Bramley"], "writes": [6, 8, 13, 16, 20, 38]}}
  die check:persuasion check success 1d20=14
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Roger", "why": "Roger is too busy cooking to be bothered by a greeting."}
  · {"decision": "name_is_a_person", "name": "Arnulf Bramley", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "face", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_enter", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  · {"decision": "placed_in_scene", "name": "Arnulf Bramley", "unknown_place": "behind the bar", "place": "The Shears and Wheel"}
  · {"decision": "filed_at_player_place", "code": "B", "name": "Arnulf Bramley", "was": 2, "now": 1, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Arnulf Bramley"]}
  prose end: at might be pipe smoke. As you approach the bar, you notice the man's eyes narrow slightly as he takes in your appearance. He doesn't speak until you've drawn near enough to hear him over the low chatter of the room. "Evening," he says. "This your first time?"

## T5 (19.66s, 0 calls)
  > I tell the barman I am Wren, Hesper's apprentice, and ask if he knows of any paid work, and what the notice for skilled labor pays.
  at Thornhallow | gold 12 | hp 20 | energy 15 | +5 min
  new rows: {"quests": {"rows": ["#2 helping hands"], "writes": [33, 34, 35]}, "quest_steps": {"rows": ["#2 helping hands"], "writes": [36]}}
  die check:persuasion check success 1d20=15
  · {"decision": "absent_not_an_opponent", "names": ["Arnulf Bramley"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most people in Hesper's inn would be happy to share information about available work and wages, as it ben
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "sketch_identity_asked", "name": "Arnulf Bramley", "asked": ["A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Arnulf Bramley", "evidence": "quests.giver_npc_id"}
  prose end: wn his rag and considers you for a moment. "Well now, an apprentice mage looking to earn some coin, are ye? There's always need for helping hands in a town like this," he says. "Saw a notice posted round here for skilled labor - did you have your eye on that?"

## T6 (15.68s, 0 calls)
  > Yes, I do. I ask Arnulf what the skilled labor job pays and who I report to.
  at Thornhallow | gold 12 | hp 20 | energy 15 | +5 min
  coins in prose: ['Fifteen gold']
  die check:persuasion check success 1d20=7
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["B", "A"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Arnulf Bramley", "why": "Most people in Arnulf's position would be willing to share information about job pay
  · {"decision": "noun_is_no_figure", "kind": "arm", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Aye, skilled. What's the pay?"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  prose end: the base of a hillside forest, surrounded by tall pines that sway gently in the morning breeze. Shafts of sunlight pierce through the branches and dapple the yard with golden spots. The scent of fresh-cut wood mingles with the earthy aroma of the nearby woods.

## T7 (17.53s, 0 calls)
  > I accept the work. I ask Arnulf what I actually have to do today and whether any of the pay comes in advance.
  at Thornhallow | gold 12 | hp 20 | energy 15 | +5 min
  new rows: {"gm_events": {"rows": ["#1 Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present."], "writes": [31]}}
  die check:persuasion check success 1d20=6
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["B", "A"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Arnulf Bramley", "why": "The barkeep is expecting the worker and has no reason to refuse the request."}
  · {"decision": "speech_said_before_dropped", "lines": ["\"And pay fifteen gold pieces for good workers.\"", "\"Ye'll report to me,\" he says, wiping his hands on his apron."]}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "refused", "item": {"name": "gold coin", "tokens": ["gold", "coin"], "outcome": "unshown_loss"}}
  prose end: pped against the wall. "Aye, sweep the floors first," he says. "Then see to the tables as they're emptied. The regulars can be a messy bunch!" He chuckles heartily at his own joke before turning to serve a customer who just called out for another round of ale.

## T8 (18.41s, 0 calls)
  > I take the broom and sweep the taproom floor, working around the tables.
  at Thornhallow | gold 12 -> 27 | hp 20 | energy 12 | +25 min
  inv + ['ITEM broom x1']
  new rows: {"npcs": {"rows": ["#3 Patron 1", "#4 Patron 2"], "writes": [16, 17, 20, 21, 62]}, "quests": {"rows": ["#3 Floor-cleaning"], "writes": [48, 49, 50, 54, 61]}, "quest_steps": {"rows": ["#3 clean the floor"], "writes": [51, 53]}}
  die player.gold_delta 2d6+3=-7 (turn_bands)
  die skill:Athletics skill_gain trivial 1=1
  die check:athletics check critical_success 1d20=22
  die unnamed_count:patron figure_count patron 1d4+1=2
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A"]}
  · {"decision": "name_is_a_person", "name": "Brida", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "at The Shears and Wheel", "confirm": "Yes, you are"}
  · {"decision": "model_reward_dropped", "quests": [2], "fields": ["xp_band"], "why": "the quest parser finishes and pays this job"}
  · {"decision": "loss_not_shown", "gold_delta": -7, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "model_reward_dropped_for_quest_payout", "fields": ["xp_band"]}
  · {"decision": "unnamed_figure_numbered", "name": "Patron 1", "code": "C", "attitude": "neutral", "by": "record"}
  · {"decision": "unnamed_figure_numbered", "name": "Patron 2", "code": "D", "attitude": "neutral", "by": "record"}
  · {"decision": "unstated_count_rolled", "kind": "patron", "phrase": "A few curious patrons", "notation": "1d4+1", "rolls": [1], "count": 2, "prose_written": true, "summary_written": false}
  · {"decision": "paid", "quest": "Q2", "action": "step_done", "paid": {"gold": 15, "xp": 25, "karma": 0, "items": [], "units": 1, "text": "+15 gold, +25 XP", "money_units": 150000, "settled": 15, "source": "parser"}, "quote
  · {"decision": "pencilled_in", "names": ["Patron 1", "Patron 2"]}
  prose end: rsations inside. As you finish up, the kitchen hand Roger [[A]] approaches, wiping his hands on his apron. "Fine job," he says approvingly. "You've a knack for this floor-cleaning. Think about staying on. The Shears and Wheel could use regular help like this."

## T9 (12.73s, 0 calls)
  > I ask Arnulf whether the pay for sweeping is settled, and how much I just earned.
  at Thornhallow | gold 27 | hp 20 | energy 12 | +5 min
  coins in prose: ['15 gold']
  die check:persuasion check success 1d20=15
  · {"decision": "attack_target_absent", "absent": {"code": "B", "name": "Arnulf Bramley", "place": "L2", "place_name": "The Shears and Wheel", "dead": false}, "rolled": false, "not_the_lines": null}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "It is reasonable for the player's character to ask about payment for work done."}
  · {"decision": "gain_without_coin_dropped", "stated": 15, "why": "the prose shows no coin reaching the player"}
  · {"decision": "refused", "item": {"name": "gold coin", "tokens": ["gold", "coin"], "outcome": "unshown_loss"}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  · {"decision": "figure_is_one_here", "kind": "patron", "names": ["Patron 1", "Patron 2"]}
  · {"decision": "sketch_confirmed", "name": "Patron 1", "evidence": "ops"}
  · {"decision": "sketch_confirmed", "name": "Patron 2", "evidence": "ops"}
  prose end: ll out to Arnulf, "Arnulf! Is the room rate for sweeping settled?" Roger [[A]] pauses his sweeping to listen, then calls over, "He's not here right now. I'll tell you what he said - 15 gold pieces for today's sweep. That includes the taproom and common areas."

## T10 (21.64s, 0 calls)
  > I buy a loaf of bread from Roger. I offer three copper for it.
  at Thornhallow | gold 27 | hp 20 | energy 12 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "C", "D"]}
  · {"decision": "model_move_dropped", "destination": "Thornhallow [[L1]]", "why": "not_a_place"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "settled", "detail": {"source": "offer_unanswered", "offer": 0.0003, "gold_delta": 0, "money_delta": 0}}
  prose end: ork - but this seems like more trouble than it's worth. Maybe you should just buy some bread and get out of town. Roger [[A]] steps out from behind the counter, wiping his hands on a towel. "You're back," he says. "I told that floor-cleaner you'd be in today."

## T11 (31.84s, 0 calls)
  > I ask @A again: will he sell me a loaf of bread for three copper?
  at Thornhallow | gold 27 -> 16 | hp 20 | energy 12 | +5 min
  coins in prose: ['three copper', 'six copper']
  die player.gold_delta 2d6+3=-11 (turn_bands)
  die check:persuasion check success 1d20=17
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "C", "D"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Roger", "why": "Roger is busy baking and might have few extra loaves, but won't want to sell at such a low pr
  · {"decision": "speech_said_before_dropped", "lines": ["\"I told that floor-cleaner you'd be in today.\""]}
  · {"decision": "pay_in_another_unit", "title": "Bread Sale", "gold": 3}
  · {"decision": "name_is_a_person", "name": "Ralf Upcott", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "checked_offer_kept", "title": "Bread Sale", "keyword_verdict": "no_offer_in_exchange"}
  · {"decision": "agreed_price_set", "code": "Q3", "from": 15, "to": 0.0003, "how": "player_terms_agreed", "per_day": false}
  prose end: ods. "Ah, you're back," he says. "I need bread," you tell him. "Can I have a loaf for three copper?" Roger [[A]] considers this briefly. "Aye, if the bread's still fresh from this morn," he replies. "That'll be six copper though - the price goes up past noon."

## T12 (19.95s, 0 calls)
  > I pay Roger six copper for the loaf of bread.
  at Thornhallow | gold 16 -> 15 | hp 20 | energy 13 | +6 min
  inv + ['loaf of bread x1']
  new rows: {"npcs": {"rows": ["#5 Patron 3"], "writes": [12, 13, 16, 17, 36, 43]}}
  coins in prose: ['Six copper']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "C", "D"]}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "player_paid_outright", "amount": 0.0006, "line": "I pay Roger six copper for the loaf of bread."}
  · {"decision": "take_of_unowned_read_as_gain", "item": "loaf of bread", "quantity": 1}
  · {"decision": "trade_settled", "kind": "purchase", "items": ["loaf of bread"], "price_units": 6, "price": "6 copper", "price_from": "line", "money_delta": -6, "gold_delta": 0, "was": -6, "gold_changed": false}
  · {"decision": "settled", "detail": {"source": "player_paid", "gold_delta": -0.0006, "offer": 0.0006, "model": null, "money_delta": -6}}
  · {"decision": "unnamed_figure_numbered", "name": "Patron 3", "code": "E", "attitude": "neutral", "by": "record"}
  · {"decision": "pencilled_in", "names": ["Patron 3"]}
  prose end: orner table are engaged in low conversations, occasionally glancing up at you as they eat their meals. The one by the counter is more interested in the tankard of ale in his hand, taking a long sip before setting it down and looking over at you with curiosity.

## T13 (14.8s, 0 calls)
  > I eat the bread, then ask @A where I can find the Chandlers' Guild and how much of Hesper's debt it will take.
  at Thornhallow | gold 15 | hp 20 | energy 13 | +5 min
  die check:persuasion check success 1d20=11
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "C", "D", "E"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Roger", "why": "A kitchen hand might help a fellow servant but is unlikely to risk their job by asking about 
  · {"decision": "speech_said_before_dropped", "lines": ["\"Good. If you want bread, I've got fresh loaves from this morn\u2014\"", "\"Ah, you're finally here,\" Roger [[A]] says with a smile as you approach."]}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  prose end: ere would be a start." He leans in closer. "Between you and me, if you can get him to take on some work around the tavern, I wouldn't mind smoothing things over." The bread was good but you're still hungry - maybe some of that work will be to your benefit too.

## T14 (9.46s, 0 calls)
  > I leave the tavern and walk to the Chandlers' Guild hall.
  at Thornhallow -> the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +6 min
  new rows: {"npcs": {"rows": ["#6 Woman 1"], "writes": [14, 15, 19, 41, 42]}, "locations": {"rows": ["#3 the Chandlers' Guild hall"], "writes": [9, 10, 11, 18]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "C", "D", "E"]}
  · {"decision": "noun_is_no_figure", "kind": "shawl", "by": "ask", "first": false, "check": null}
  · {"decision": "setup_names_this_kind", "kind": "guild_hall", "size": "village"}
  · {"decision": "same_name_other_spelling", "name": "Chandlers' Guild hall", "known": "the Chandlers' Guild hall"}
  · {"decision": "same_name_other_spelling", "name": "Chandlers' Guild hall", "known": "the Chandlers' Guild hall"}
  · {"decision": "pencilled_in", "names": ["Woman 1"]}
  · {"decision": "sketch_identity_asked", "name": "Woman 1", "asked": ["A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Woman 1", "evidence": "locations.keeper_npc_id"}
  prose end:  with loaves piled high; a smith working at his forge, the glow of the fire casting flickering light on his face; an old woman in a shawl who watches you pass with curious eyes. You can smell baking and hear the clanging of the blacksmith's hammer as you walk.

## T15 (12.96s, 0 calls)
  > I walk up to the guild hall door, go in and greet the first guild clerk I see. I ask what Hesper's debt stands at.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +5 min
  new rows: {"gm_events": {"rows": ["#2 Off-screen movement continues around the Chandlers' Guild hall."], "writes": [24]}}
  die check:persuasion check success 1d20=15
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Woman 1", "why": "Most people would not refuse to answer a simple question about a guild member's debt status
  · {"decision": "quote_said_by_a_person", "quote": "You there!"}
  · {"decision": "venue_kind_only_names_the_owner", "kind": "guild_hall", "head": ["door"]}
  · {"decision": "venue_requested_made", "destination": "the Chandlers' Guild hall"}
  · {"decision": "move_held_where_ended_confirmed", "destination": "the Chandlers' Guild hall", "answer": "still in the Chandlers' Guild hall", "rule": "venue_requested"}
  prose end: wood polish and spices - a reminder of the bustling trade that fuels this guild's coffers. At the front desk sits an unnamed woman, her hands busy with parchment as she records transactions. "You there!" she calls out without looking up. "State your business."

## T16 (12.69s, 0 calls)
  > I tell her I am Wren Ashcombe, Hesper's apprentice, and ask how much of the three years of wax is still owed.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +5 min
  new rows: {"npcs": {"rows": ["#7 Bryony"], "writes": [6, 8, 13, 16, 18, 31, 35]}}
  die check:persuasion check success 1d20=14
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Woman 1", "why": "The woman recognizes Hesper's apprentice and is likely to honor the debt."}
  · {"decision": "name_is_a_person", "name": "Bryony", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "placed_in_scene", "name": "Bryony", "unknown_place": "[[L3]]", "place": "L3"}
  · {"decision": "figure_is_one_here", "kind": "woman", "names": ["Woman 1"]}
  · {"decision": "pencilled_in", "names": ["Bryony"]}
  prose end: kept - the woman's work is evidently good. Perhaps the guild moves slowly, or keeps its accounts in the old way. A year of tending hearth and making wax may keep you busy enough. The unnamed woman nods, not unkindly. "As you will it. Welcome to your new post."

## T17 (22.19s, 0 calls)
  > I correct her: I did not come for wages. I say Hesper died owing the guild wax and I ask @G how many silver I must pay to keep the cottage.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +5 min
  die check:persuasion check success 1d20=16
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["G", "F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Bryony", "why": "Bryony is expecting payment from Hesper, but may accept a small amount to avoid trouble with
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "sketch_faded", "name": "Patron 3", "made": 13, "unmentioned_turns": 5}
  · {"decision": "sketch_identity_asked", "name": "Bryony", "asked": ["F", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Bryony", "evidence": "ops"}
  prose end: ll keep a roof over your head at least. You've come to an agreement with the guild steward. The weight of the situation hangs heavy in the air as you stand firm, ready to make amends for Hesper's unpaid debt while maintaining some control over your own future.

## T18 (14.58s, 0 calls)
  > I offer @G one silver now toward Hesper's debt and ask her to write it in the guild's book.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +5 min
  die check:persuasion check success 1d20=16
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["G", "F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Bryony", "why": "Bryony would likely accept the offer of partial payment on Hesper's debt, as it helps resolv
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "figure_is_listed_person", "hint": "an unnamed woman"}
  · {"decision": "figure_is_known_person", "hint": "a young woman"}
  · {"decision": "figure_is_listed_person", "hint": "a middle-aged man"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end:  month's fee," interrupts a man's voice. You turn to see a middle-aged man in guild robes approaching from the back of the hall. Bryony [[G]] dips her head and gestures with her broom. "I'll write it down for you, Master Dyer," she says. "How much will it be?"

## T19 (13.13s, 0 calls)
  > I take one silver coin from my purse and hand it to @G as a payment on the debt.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +6 min
  die player.gold_delta 2d6+3=-11 (turn_bands)
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["G", "F"]}
  · {"decision": "name_is_a_person", "name": "Kendra Furlong", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "payment_unpriced_banded", "band": "-small"}
  · {"decision": "loss_not_shown", "gold_delta": -11, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "payment_unpriced_band", "band": "-small", "offer": null}}
  · {"decision": "figure_is_one_here", "kind": "woman", "names": ["Woman 1"]}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: expression softening as she does so. "Thank you," she says quietly. "I'll make sure this goes to a good cause." The woman at the hearth glances over, then returns to stirring her pot. You have paid your monthly fee to use Thornhallow [[L1]]'s guild facilities.

## T20 (11.37s, 0 calls)
  > I step aside, open Hesper's brass-bound grimoire and try to read the first page with my Old Script.
  at the Chandlers' Guild hall | gold 15 | hp 20 | energy 13 | +15 min
  die check:investigation check critical_success 1d20=22
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F", "G"]}
  · {"decision": "noun_is_no_figure", "kind": "page", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "line", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "chill", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  prose end:  [[G]], glances up and nods in approval at your efforts. At last, a line of script leaps out at you from the page: "Who lights it shall be lit by its fire." You feel a chill. This grimoire holds power. Perhaps too much for an apprentice like yourself to wield.

## T21 (14.66s, 0 calls)
  > I leave the guild hall and walk out of Thornhallow along the old King's Road toward the ruins in the Greywold hills.
  at the Chandlers' Guild hall -> Thornhallow | gold 15 | hp 20 | energy 12 | +6 min
  new rows: {"npcs": {"rows": ["#8 Face 1", "#9 Face 2", "#10 Face 3", "#11 Face 4"], "writes": [14, 15, 18, 19, 20, 23, 24, 25, 28, 29, 30, 33, 58]}, "locations": {"rows": ["#4 Greywold Ruins"], "writes": [9, 10]}, "events": {"rows": ["#1 Ruins Exploration"], "writes": [11, 35]}}
  die unnamed_count:face figure_count face 1d4+1=4
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F", "G"]}
  · {"decision": "place_left_not_destination", "place": "Thornhallow"}
  · {"decision": "place_left_not_destination", "place": "Thornhallow"}
  · {"decision": "name_is_a_person", "name": "Osric Dunning", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "cloudy", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_a_figure", "kind": "face", "by": "ask", "first": true, "check": true}
  · {"decision": "figure_not_hostile", "kind": "face"}
  · {"decision": "place_left_not_destination", "place": "Thornhallow"}
  · {"decision": "left_a_thing_not_the_place", "place": "the Chandlers' Guild hall"}
  · {"decision": "place_left_not_destination", "place": "Thornhallow"}
  · {"decision": "place_left_not_destination", "place": "Thornhallow"}
  · {"decision": "unfinished_tail_repaired", "why": "unfinished_tail", "text": "==="}
  · {"decision": "unnamed_figure_numbered", "name": "Face 1", "code": "H", "attitude": "neutral", "by": "ask"}
  · {"decision": "unnamed_figure_numbered", "name": "Face 2", "code": "I", "attitude": "neutral", "by": "ask"}
  · {"decision": "unnamed_figure_numbered", "name": "Face 3", "code": "J", "attitude": "neutral", "by": "ask"}
  · {"decision": "unnamed_figure_numbered", "name": "Face 4", "code": "K", "attitude": "neutral", "by": "ask"}
  · {"decision": "unstated_count_rolled", "kind": "face", "phrase": "a few familiar faces", "notation": "1d4+1", "rolls": [3], "count": 4, "prose_written": true, "summary_written": false}
  · {"decision": "pencilled_in", "names": ["Face 1", "Face 2", "Face 3", "Face 4"]}
  prose end: ars on. No other travelers or creatures are sighted during your time here. Eventually, you turn back and retrace your steps to Thornhallow [[L1]], arriving with the last light of dusk. The air there feels safer somehow compared to the eerie quiet of the ruins.

## T22 (9.37s, 0 calls)
  > I go to #L4, walk up to the ruins and enter the crumbling gateway.
  at Thornhallow -> Greywold Ruins | gold 15 | hp 20 | energy 12 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["H", "I", "J", "K"]}
  · {"decision": "place_bound_by_reference", "code": "L4", "place": "Greywold Ruins", "words": "Greywold Ruins"}
  · {"decision": "name_is_a_person", "name": "Ulric Yardley", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "temple", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "gateway", "by": "ask", "first": false, "check": null}
  · {"decision": "player_code_travel", "code": "L4", "destination": "Greywold Ruins", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "outside Thornhallow, on the road or in the wilds", "destination": "Greywold Ruins"}
  · {"decision": "new_place_in_town", "place": "Greywold Ruins", "town": "Thornhallow"}
  prose end: y on the left side that looks more passable. The interior is overgrown with mossy vines and dead branches. Piles of rubble litter the floors and block off paths. The pillared hall leads deeper into the ruins. You can hear the drip of water echoing from within.

## T23 (10.84s, 0 calls)
  > I call Candlelight to light my palm, then search the rubble and the floor of the pillared hall for tracks, old script or anything useful.
  at Greywold Ruins | gold 15 | hp 20 | energy 10 | +15 min
  new rows: {"gm_events": {"rows": ["#3 Off-screen movement continues around Greywold Ruins."], "writes": [24]}}
  die skill:Omen Reading skill_gain small 1=1
  die check:perception check success 1d20=13
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "the Chandlers' Guild hall", "words": "hall"}
  · {"decision": "name_is_a_person", "name": "Stephen Quarrel", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Greywold Ruins", "status": "not_travel"}
  · {"decision": "same_name_other_spelling", "name": "Greywolds Ruins", "known": "Greywold Ruins"}
  prose end: You step carefully over the fallen stones, Candlelight in hand. The beam of light picks out fresh tracks among the rubble and casts shadows on the weathered script etched into the walls. You trace the lines with your eyes, hoping to find a clue.

## T24 (9.24s, 0 calls)
  > I follow the fresh tracks deeper into the ruins, ready to defend myself if something is there.
  at Greywold Ruins | gold 15 | hp 20 | energy 10 | +6 min
  · {"decision": "name_is_a_person", "name": "Bertha Ilsley", "by": "ask", "why": "op_person"}
  · {"decision": "model_move_dropped", "destination": "Thornhallow [[L1]]", "why": "not_a_place"}
  · {"decision": "same_name_other_spelling", "name": "Greywolds Ruins", "known": "Greywold Ruins"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "dagger", "quantity": 1}
  · {"decision": "refused", "item": {"name": "dagger", "tokens": ["dagger"], "outcome": null, "taken_unasked": false}}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: rumbling walls. You keep going, drawn by curiosity and a sense of unease as to what or who might have left those tracks. There are no signs of recent habitation in this part of Greywolds - just cracked tiles, toppled statues and the occasional whisper of wind.

## T25 (9.57s, 0 calls)
  > !wait 360 sleep
  at Greywold Ruins | gold 15 | hp 20 | energy 15 | +360 min
  · {"decision": "noun_is_no_figure", "kind": "room", "by": "ask", "first": false, "check": null}
  prose end:  lie discarded on the floor, their wicks long since consumed. As you rummage through the debris looking for anything salvageable, your hand closes around a smooth wooden handle. It's an old scroll tube that looks to have survived better than most of the books.

## T26 (12.48s, 0 calls)
  > I stand up in the ruins, stretch, and follow the fresh tracks past the pillared hall into the next chamber, hand on my belt.
  at Greywold Ruins -> Deeper Into Ruins | gold 15 | hp 20 | energy 15 | +6 min
  new rows: {"locations": {"rows": ["#5 Deeper Into Ruins"], "writes": [13, 14, 34, 54, 74, 94]}, "events": {"rows": ["#2 Following fresh tracks, you find yourself navigating a maze of chambers deep in the heart of Greywou"], "writes": [15, 17]}}
  die skill:perception skill_gain small 1=1
  · {"decision": "new_place_not_shown", "name": "a chamber within Greywound"}
  · {"decision": "sketch_faded", "name": "Face 1", "made": 22, "unmentioned_turns": 5}
  · {"decision": "sketch_faded", "name": "Face 2", "made": 22, "unmentioned_turns": 5}
  · {"decision": "sketch_faded", "name": "Face 3", "made": 22, "unmentioned_turns": 5}
  · {"decision": "sketch_faded", "name": "Face 4", "made": 22, "unmentioned_turns": 5}
  prose end: low fresh tracks through the rubble past the towering pillars into the next chamber. The air here smells faintly of smoke and damp stone. Ahead, a pair of tracks diverges - one heading deeper into the ruins, the other towards Thornhallow [[L1]]'s shadowy bulk.

## T27 (10.83s, 0 calls)
  > I take the tracks leading deeper into the ruins and listen for anything moving ahead of me.
  at Deeper Into Ruins | gold 15 | hp 20 | energy 14 | +6 min
  new rows: {"npcs": {"rows": ["#12 Person 1"], "writes": [11, 12, 36]}, "quest_steps": {"rows": ["#4 Tracked, listened"], "writes": [32, 33]}, "gm_events": {"rows": ["#4 faint signs of life"], "writes": [15]}}
  die check:survival check partial 1d20=9
  · {"decision": "common_noun_names_known_place", "noun": "ruins", "place": "Greywold Ruins"}
  · {"decision": "walk_inside_another_intent", "primary": "investigation", "destination": "Greywold Ruins"}
  · {"decision": "common_noun_names_known_place", "noun": "ruins", "place": "Greywold Ruins"}
  · {"decision": "model_move_replaced_by_player_destination", "model_destination": "Deeper Into Ruins", "player_destination": "Greywold Ruins"}
  · {"decision": "server_move_not_shown", "destination": "Greywold Ruins", "rule": "player_named"}
  · {"decision": "unnamed_figure_numbered", "name": "Person 1", "code": "H", "attitude": "neutral", "by": "record"}
  · {"decision": "pencilled_in", "names": ["Person 1"]}
  prose end: nd listen intently, trying to make out more details from the sounds. But the ruins are thick with echoes that play tricks on your ears. After a moment, you continue forward once more, the decision of whether to investigate those noises left hanging in the air.

## T28 (11.24s, 0 calls)
  > I creep toward the rustling sound with my hand ready to defend myself, and call out: who is there?
  at Deeper Into Ruins | gold 15 | hp 20 | energy 14 | +6 min
  die check:stealth check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["H"]}
  · {"decision": "quote_said_by_a_person", "quote": "Who are you?"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes"}
  prose end: The rustling grows louder as you approach. A shape emerges from the shadows - an unnamed person, their face half-hidden by a hood. "Who are you?" they call out sharply, voice tense with fear or warning.

## T29 (15.95s, 0 calls)
  > I tell the hooded figure I am Wren, Hesper's apprentice, and I mean no harm; I ask what they are doing in the ruins.
  at Deeper Into Ruins | gold 15 | hp 20 | energy 14 | +5 min
  new rows: {"npcs": {"rows": ["#13 Figure 1"], "writes": [11, 13, 14, 31, 40]}, "quests": {"rows": ["#4 Seek Hidden Knowledge"], "writes": [35, 36, 37]}, "quest_steps": {"rows": ["#5 I seek knowledge hidden here, knowledge others have forgotten or were not worthy to remember."], "writes": [38]}}
  die skill:perception skill_gain trivial 1=1
  die check:persuasion check success 1d20=16
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["H"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most people in Wren's position would be curious and polite when encountering a stranger in ruins, trying 
  · {"decision": "name_is_a_person", "name": "Lyra", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_one_here", "kind": "figure", "names": ["Figure 1"]}
  · {"decision": "checked_offer_kept", "title": "Seek Hidden Knowledge", "keyword_verdict": "no_offer_in_exchange"}
  · {"decision": "pencilled_in", "names": ["Figure 1"]}
  prose end: ith sharp features. "I seek knowledge hidden here, knowledge others have forgotten or were not worthy to remember." She eyes your outfit and the staff at your side. "And what of you? An apprentice wandering alone in the wilds - are you running from something?"

## T30 (18.75s, 0 calls)
  > I say I am not running from anything, and ask her name and what knowledge she is after.
  at Deeper Into Ruins | gold 15 | hp 20 | energy 14 | +5 min
  new rows: {"npcs": {"rows": ["#14 Gisela"], "writes": [6, 9, 14, 36, 37]}}
  die check:persuasion check partial 1d20=8
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["H", "M"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Person 1", "why": "Most ordinary people would not refuse to answer such a simple question."}
  · {"decision": "name_is_a_person", "name": "Gisela", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "placed_in_scene", "name": "Gisela", "unknown_place": "Deeper Into Ruins [[L5]]", "place": "L5"}
  · {"decision": "figure_is_one_here", "kind": "figure", "names": ["Figure 1"]}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Gisela"]}
  · {"decision": "sketch_identity_asked", "name": "Figure 1", "asked": ["H"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Figure 1", "evidence": "ops"}
  prose end: It's evening, and the light is fading as you approach the unnamed figure. She looks up from her work with a dismissive frown. "Running from something?" she asks. "What sort of fool talks to strangers in ruins?" The name is Wren.

## T31 (16.69s, 0 calls)
  > I ask @N again, politely, what she is searching for, and offer to light the way with Candlelight so she can read the walls.
  at Deeper Into Ruins | gold 15 | hp 20 | energy 13 | +15 min
  new rows: {"gm_events": {"rows": ["#5 A delayed consequence of recent public actions continues off-screen."], "writes": [31]}}
  die check:persuasion check success 1d20=10
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "H", "M"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Gisela", "why": "Gisela is focused on her task and doesn't need assistance."}
  · {"decision": "stays_as_shown", "place": "Deeper Into Ruins", "status": "not_travel"}
  · {"decision": "sketch_identity_asked", "name": "Gisela", "asked": ["M", "H"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Gisela", "evidence": "prose_code"}
  prose end: w steady as it hovers there. "I can light our way if you like," you offer. Gisela [[N]] pauses her search for a moment to look over at you. The light from Candlelight casts shadows across her face, revealing a thoughtful expression as she considers your words.

## T32 (10.82s, 0 calls)
  > I offer to sell @N my loaf of bread for four copper, since she looks hungry after a long search.
  at Deeper Into Ruins | gold 15 -> 27 | hp 20 | energy 13 | +15 min
  coins in prose: ['Four copper', 'four copper', 'Six copper']
  die player.gold_delta 2d6+3=12 (turn_bands)
  die check:perception check partial 1d20=9
  · {"decision": "attack_ask_aim_only", "codes": ["N"]}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["H", "M"]}
  · {"decision": "name_is_a_person", "name": "Melisent Wadley", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "apple", "quantity": 1}
  · {"decision": "refused", "item": {"name": "bread", "tokens": ["bread"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "apple", "tokens": ["apple"], "outcome": null, "taken_unasked": false}}
  · {"decision": "sketch_faded", "name": "Person 1", "made": 28, "unmentioned_turns": 5}
  prose end: ead looks good and she missed lunch, but four copper seems too little for something that will keep her going. She'd have to buy another loaf later at the cost of the first. "Six copper," Gisela [[N]] counters finally. "And I'll throw in an apple from my pack."

## T33 (13.88s, 0 calls)
  > I agree to six copper and hand @N the loaf of bread. I decline the apple.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 13 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "M"]}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "declined_by_player", "quest": "Q4", "was": "offered"}
  prose end: u turn to walk away from Deeper Into Ruins [[L5]]. The air is cool and quiet, the only sounds being the crunch of gravel underfoot and distant bird calls. You can make out the crumbling towers of the old city on the horizon, silhouetted against the orange sky.

## T34 (10.37s, 0 calls)
  > I walk back toward the entrance and then up the hill track, looking for the source of the smoke I smelled, ready to run or fight if anything hostile shows itself.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 12 | +8 min
  die check:melee check success 1d20=14
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "M"]}
  · {"decision": "speech_said_before_dropped", "lines": ["\"Six copper. That's a fair price for a day's journey's rations.\""]}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: them, the same woman who sold you rations earlier in the day. She sees you and waves you over. "Glad to see you're still about," she calls out as you near the camp. "Join us for a meal? We've got more firewood than we can chop before dark." Gisela [[N]] grins.

## T35 (10.28s, 0 calls)
  > I thank Gisela but decline the meal, and go down into the deepest dark chamber of the ruins, calling Candlelight to see what made the other set of tracks.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 11 | +6 min
  die check:survival check failure 1d20=4
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "M"]}
  · {"decision": "venue_needs_a_settlement", "place": "Deeper Into Ruins"}
  · {"decision": "stays_as_shown", "place": "Deeper Into Ruins", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: dden alcove carved deep within the stone walls. Pausing at its entrance, you can make out faint markings etched into the floor – strange sigils that hint at some long-forgotten magic. Cautiously, you step forward into the dimly lit alcove, your heart pounding.

## T36 (15.22s, 0 calls)
  > I kneel at the sigils in the alcove and use Old Script to read them aloud, while my Candlelight shows the tracks; I watch the dark behind me.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 9 | +15 min
  new rows: {"gm_events": {"rows": ["#6 ."], "writes": [14]}}
  die check:symbol_lore check success 1d20=21
  · {"decision": "attack_ask_aim_only", "codes": ["N", "M"]}
  · {"decision": "deed_not_a_task_phrase", "title": "skilled labor", "why": "scene_sentence", "answer": "The player kneels at the sigils in the alcove, using Old Script to read them aloud and showing the tracks with Candleli
  · {"decision": "stays_as_shown", "place": "Deeper Into Ruins", "status": "not_travel"}
  prose end: ir search. Gisela [[N]] watches with interest as I read, her own eyes sharp. "You've found your way into something old and deep," she comments. "Best be careful what secrets you stir up. These ruins have not forgotten the last folk who sought their treasures."

## T37 (9.79s, 0 calls)
  > I press on past the alcove down the narrow passage the old tracks follow, my Candlelight held out ahead, and listen for growls.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 7 | +6 min
  die skill:strength skill_gain trivial 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["M", "N"]}
  · {"decision": "role_was_a_note", "name": "Gisela", "note": "works at Deeper Into Ruins"}
  · {"decision": "stays_as_shown", "place": "Deeper Into Ruins", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: ats. The only sound you hear is your own breathing and the distant drip of water somewhere. As you stand there waiting, Gisela [[N]] emerges from one of the side passages and approaches you cautiously. She eyes your Candlelit palm curiously but does not speak.

## T38 (9.5s, 0 calls)
  > I step into the left corridor alone and shout into the dark, challenging whatever lives here to show itself.
  at Deeper Into Ruins | gold 27 | hp 20 | energy 7 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["M", "N"]}
  · {"decision": "venue_needs_a_settlement", "place": "Deeper Into Ruins"}
  · {"decision": "narration_code_skipped", "code": "L1", "why": "origin_or_denied"}
  · {"decision": "stays_as_shown", "place": "Deeper Into Ruins", "status": "unresolved"}
  · {"decision": "figure_is_listed_person", "hint": "a figure"}
  · {"decision": "figure_is_listed_person", "hint": "a traveler"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end:  to wander these ruins alone at night." "What brings a traveler like you to Deeper Into Ruins?" Gisela [[N]] asks, lowering her guard slightly as she takes a step closer. You have an opening - but do you press it? Or play along with this stranger's small talk?

## T39 (13.79s, 0 calls)
  > I tell @N I am leaving #L5 for #L4 and ask her whether she has seen any wolves, goblins or bandits on the hills.
  at Deeper Into Ruins -> Greywold Ruins | gold 27 | hp 20 | energy 7 | +5 min
  new rows: {"gm_events": {"rows": ["#7 Off-screen movement continues around Greywold Ruins."], "writes": [33]}}
  die check:persuasion check success 1d20=19
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "M"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "Gisela is focused on her work and doesn't pay much attention to travelers passing through."}
  · {"decision": "place_bound_by_reference", "code": "L4", "place": "Greywold Ruins", "words": "Greywold Ruins"}
  · {"decision": "player_code_travel", "code": "L4", "destination": "Greywold Ruins", "replaced": "#L4"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: on the paths if you can." Her expression turns curious. "Why do you ask? Planning to explore further into the ruins?" She seems to consider offering more, but then shakes her head. "Best of luck to you then. And stay alert out there." "I'll keep that in mind."

## T40 (17.75s, 0 calls)
  > I leave the ruins and climb the open hillside above the old road, keeping to the paths, searching for wolf tracks or a bandit camp.
  at Greywold Ruins -> Outside Thornhallow | gold 27 | hp 20 | energy 5 | +10 min
  new rows: {"locations": {"rows": ["#6 Outside Thornhallow"], "writes": [9, 12]}}
  die check:perception check success 1d20=20
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "noun_is_no_figure", "kind": "rise", "by": "ask", "first": false, "check": null}
  · {"decision": "model_move_dropped", "destination": "[[L5]] an abandoned watchtower on a hilltop several miles ahead.", "why": "not_a_place"}
  · {"decision": "outside_place_made", "name": "Outside Thornhallow", "outside_of": "Thornhallow"}
  · {"decision": "move_from_prose", "destination": "Outside Thornhallow", "kind": "outside", "status": "unresolved"}
  prose end: nous state. But it will offer cover and a good view of the surrounding area. The ground is rough going - loose rock and tufts of coarse grass slow your progress. But you keep at it, driven by curiosity about what you might find inside the abandoned watchtower.

## T41 (11.26s, 0 calls)
  > I walk to the abandoned watchtower, step inside carefully, and look around for anyone camped there.
  at Outside Thornhallow | gold 27 | hp 20 | energy 4 | +6 min
  new rows: {"locations": {"rows": ["#7 Outside Thornhallow Supplies"], "writes": [6, 7]}}
  die check:perception check success 1d20=14
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "venue_needs_a_settlement", "place": "Outside Thornhallow"}
  · {"decision": "setup_names_this_kind", "kind": "general_store", "size": "hamlet"}
  · {"decision": "setup_names_this_kind", "kind": "general_store", "size": "hamlet"}
  prose end: ts flickering shadows that dance across the weathered stone as you continue searching for clues about who might have been here before. Your footsteps echo softly on the floor with each careful stride forward into the unknown depths of the abandoned watchtower.

## T42 (9.35s, 0 calls)
  > I search the watchtower floor and the bedroll, and take the dried meat and one torch for myself.
  at Outside Thornhallow | gold 27 | hp 20 | energy 4 | +15 min
  inv + ['dried x1']
  die item:dried item_count small 1=1
  die skill:perception skill_gain small 1=1
  die check:perception check success 1d20=9
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "name_is_a_person", "name": "Una Hatcher", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Outside Thornhallow, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end:  is empty: its owner is gone, leaving only a hollow indent in the grass where it lay. You find nothing of value among the watchtower's supplies, but take the dried meat and one torch for yourself before descending the stairs once more. The torchlight flickers.

## T43 (9.7s, 0 calls)
  > !wait 240 sleep
  at Outside Thornhallow | gold 27 | hp 20 | energy 15 | +240 min
  die skill:in quotes then skill_gain small 1=1
  · {"decision": "name_is_a_person", "name": "Fenella Hayward", "by": "ask", "why": "op_person"}
  prose end: You sit with Gisela [[N]] in the quiet night air outside Thornhallow [[L6]], talking and watching the dark bulk of the old fortress. She's a woodcutter working at Deeper Into Ruins [[L5]] - the ruins are her real home and job site these days.

## T44 (10.8s, 0 calls)
  > I say goodnight to Gisela, leave the tower and walk down toward the old King's Road in the dark, hunting for whatever prowls the hills at night.
  at Outside Thornhallow -> Ruins | gold 27 | hp 20 | energy 15 | +6 min
  new rows: {"locations": {"rows": ["#8 Ruins"], "writes": [9, 10, 13]}, "events": {"rows": ["#3 Flicker"], "writes": [11, 17]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "name_is_a_person", "name": "Lowen Sallow", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "flicker", "by": "ask", "first": false, "check": null}
  · {"decision": "new_place_in_town", "place": "Ruins", "town": "Outside Thornhallow"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "lantern", "text": "Your lantern casts flickering beams that seem to attract more insects than they repel."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "lantern", "text": "The night is dark, but you have your lantern and a sense of purpose."}
  prose end: e scent of wild herbs from the overgrown terraces. You pause here, getting your bearings as you decide which path up the hill to take. A flicker of movement catches your eye - something dark moving between the ruins. It seems to be heading in your direction...

## T45 (13.12s, 0 calls)
  > I raise my Candlelight to see the dark shape coming at me and shout for it to stop; if it lunges I strike at it with my broom.
  at Ruins | gold 27 | hp 19 (-1) | energy 12 | +6 min
  new rows: {"events": {"rows": ["#4 A lunge"], "writes": [21]}}
  die player.gold_delta 2d6+3=-9 (turn_bands)
  die skill:melee skill_gain small 1=1
  die check:melee check failure 1d20=3
  · {"decision": "attack_found", "target": {"code": "N", "name": "Gisela"}, "source": "trigger", "skill": "", "people": []}
  · {"decision": "combat_follows_attack_check", "code": "N", "check_outcome": "failure", "was": "glancing_hit", "now": "miss", "damage": 0}
  · {"decision": "name_is_a_person", "name": "Bartholomew Garner", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "shape", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "not_travel"}
  · {"decision": "loss_not_shown", "gold_delta": -9, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  prose end: he figure vanishes in an instant, gone without a trace. Only the soft sound of your own breathing and the distant night wind through rubble remains, punctuated by the erratic flicker of your candle's flame casting eerie shadows on the cracked walls around you.

## T46 (16.15s, 0 calls)
  > I back against a pillar, call Candlelight again, and look for where the figure went, my broom held ready.
  at Ruins | gold 27 | hp 19 | energy 11 | +6 min
  new rows: {"npcs": {"rows": ["#15 Hugh Bellamy"], "writes": [13, 17, 21, 39]}, "events": {"rows": ["#5 The player follows mysterious prints"], "writes": [19]}}
  die skill:perception skill_gain small 1=1
  die check:perception check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "name_is_a_person", "name": "Hugh Bellamy", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "unresolved"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "filed_at_player_place", "code": "O", "name": "Hugh Bellamy", "was": 5, "now": 8, "why": "filed_here"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Hugh Bellamy"]}
  prose end: icks out a faint script carved into the wall. The glow reveals nothing else of note in this immediate area. You move to follow the tracks, staying close to pillars for cover as you proceed warily. The mysterious figure remains unseen, but their trail is clear.

## T47 (11.49s, 0 calls)
  > I follow the tracks quietly, and when I find whoever made them I ask @P to say who he is and why he swung at me out of the dark.
  at Ruins | gold 27 | hp 19 | energy 11 | +5 min
  new rows: {"gm_events": {"rows": ["#8 Off-screen movement continues around Ruins."], "writes": [31]}}
  die check:persuasion check failure 1d20=7
  · {"decision": "absent_not_an_opponent", "names": ["Hugh Bellamy"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "Most woodcutters would answer a stranger's question, but some might be too shy or wary to di
  · {"decision": "narration_code_skipped", "code": "L1", "why": "not_in_the_arrival_sentence"}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "unresolved"}
  · {"decision": "figure_is_listed_person", "hint": "a figure"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: stands up and steps into the moon's thin beams. It is Gisela [[N]], one of the woodcutters who work Thornhallow [[L1]]. "Who are you and what are you doing here?" she asks warily, holding a short axe loosely in her hand. "These ruins aren't safe at this hour."

## T48 (12.89s, 0 calls)
  > I tell @N I am the one who read the sigils for her hidden-knowledge search, that was @Q4, and I ask her to pay me what the job is worth.
  at Ruins | gold 27 | hp 19 | energy 11 | +15 min
  die check:persuasion check partial 1d20=5
  · {"decision": "absent_not_an_opponent", "names": ["Hugh Bellamy"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most people in @N's position would pay a freelancer for their work, especially if it was valuable for the
  · {"decision": "noun_is_no_figure", "kind": "coin", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": 15, "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  prose end: ch she pulls out. As she speaks, she upends it into your hand. A handful of gold coins spill onto your palm, glinting in the moonbeams. They feel heavy and real beneath your fingers. "Take what you deserve," Gisela [[N]] says with a wry smile. "You earned it."

## T49 (11.07s, 0 calls)
  > I count the coins she poured into my palm out loud, put them in my purse, and ask @N how much that comes to.
  at Ruins | gold 27 | hp 19 | energy 11 | +-1435 min
  new rows: {"quests": {"rows": ["#5 A name to ask after"], "writes": [11, 12, 13]}, "quest_steps": {"rows": ["#6 A name to ask after"], "writes": [14]}}
  die player.gold_delta 2d6+3=-9 (turn_bands)
  die check:persuasion check partial 1d20=2
  · {"decision": "absent_not_an_opponent", "names": ["Hugh Bellamy"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "The action is neutral and not requesting anything from @N."}
  · {"decision": "offer_names_no_task", "title": "Woodcutting", "line": "Gives a good wage for a hard day, Enough to make it worth your while."}
  · {"decision": "where_ended_not_confirmed", "answer": "in Outside Thornhallow, outside Ruins", "confirm": "Yes, you are"}
  · {"decision": "payment_unpriced_banded", "band": "-small"}
  · {"decision": "talked_to_and_shown_here", "name": "Gisela", "place": "L8"}
  · {"decision": "loss_not_shown", "gold_delta": -9, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "payment_unpriced_band", "band": "-small", "offer": null}}
  prose end: out the coins Gisela [[N]] poured into your palm. There are fifteen of them. As you put the coins in your purse, you ask Gisela [[N]] how much she's paid. "Gives a good wage for a hard day," Gisela [[N]] says with a shrug. "Enough to make it worth your while."

## T50 (10.41s, 0 calls)
  > I bid Gisela goodnight and head back to #L3, the Chandlers' Guild hall, to pay part of Hesper's debt.
  at Ruins -> Thornhallow | gold 27 | hp 19 | energy 11 | +6 min
  die player.gold_delta 2d6+3=-10 (turn_bands)
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "the Chandlers' Guild hall", "words": "the Chandlers' Guild hall", "how": "typed_and_named"}
  · {"decision": "player_code_travel", "code": "L3", "destination": "the Chandlers' Guild hall", "replaced": "#L3"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "outside Outside Thornhallow, on the road or in the wilds", "destination": "the Chandlers' Guild hall"}
  · {"decision": "loss_not_shown", "gold_delta": -10, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  prose end: moon is waning gibbous and nearly full; by its light, you pick out the familiar silhouette of the Guildhall against the starry sky. It's a good mile or more to go - the Chandlers' guild does not look kindly upon those who arrive at their door with empty hands.

## T51 (17.34s, 0 calls)
  > I walk to #L3, the Chandlers' Guild hall, to speak about Hesper's debt.
  at Thornhallow -> the Chandlers' Guild hall | gold 27 | hp 19 | energy 11 | +5 min
  die check:persuasion check partial 1d20=5
  · {"decision": "absent_not_an_opponent", "names": ["Roger", "Patron 1", "Patron 2"], "named_in_line": false}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "A few woodcutters might be willing to help a Chandler with a debt, as they often work togeth
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "the Chandlers' Guild hall", "words": "the Chandlers' Guild hall", "how": "typed_and_named"}
  · {"decision": "noun_is_no_figure", "kind": "staircase", "by": "ask", "first": false, "check": null}
  · {"decision": "player_code_travel", "code": "L3", "destination": "the Chandlers' Guild hall", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "still in Thornhallow", "destination": "the Chandlers' Guild hall"}
  · {"decision": "sketch_faded", "name": "Hugh Bellamy", "made": 47, "unmentioned_turns": 5}
  prose end: pported by ornate pillars. A wide staircase sweeps down from the second floor to your left, leading to offices and meeting rooms above. To your right is a large wooden door with "Chandlers' Guild Clerk" etched on it. You knock politely and wait for a response.

## T52 (12.75s, 0 calls)
  > I open the clerk's door and ask the clerk how much of Hesper's wax debt is still owed.
  at the Chandlers' Guild hall | gold 27 | hp 19 | energy 11 | +5 min
  new rows: {"npcs": {"rows": ["#16 Benedict"], "writes": [11, 14, 17, 35]}}
  coins in prose: ['15 gold', '6 gold', '9 gold']
  die check:persuasion check failure 1d20=3
  · {"decision": "absent_not_an_opponent", "names": ["Woman 1", "Bryony"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few people might feel it's intrusive to ask about another person's debt."}
  · {"decision": "name_is_a_person", "name": "Odelia Frome", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "clerk", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "name_fits_the_sex_shown", "given": "Odelia Frome", "drawn": "Benedict", "shown": "male"}
  · {"decision": "loss_not_shown", "gold_delta": -9, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "stated_mention", "gold_delta": 0, "offer": null, "model": -9, "money_delta": 0, "stated_delta": -9, "changed_by": "loss_not_shown"}}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "filed_at_player_place", "code": "O", "name": "Benedict", "was": 4, "now": 3, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Benedict"]}
  prose end: f writing until he finds what you're asking about. "Let's see... Hesper owes a total of 15 gold for those last two deliveries," he recites, not bothering to look up at you. "We've already paid him 6 gold upfront so that leaves a balance of 9 gold outstanding."

## T53 (12.46s, 0 calls)
  > I say I can pay part of it now, and I offer the clerk 10 silver toward the debt.
  at the Chandlers' Guild hall | gold 27 -> 40 | hp 19 | energy 12 | +6 min
  coins in prose: ['10 silver', 'Ten silvers', 'ten silvers', '10 silvers']
  die player.gold_delta 2d6+3=13 (turn_bands)
  die item:half of tonight's work item_count trivial 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "F"]}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "half of tonight's work", "quantity": 1}
  · {"decision": "refused", "item": {"name": "half of tonight's work", "tokens": ["tonight's", "work", "half"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "the other half in the morning", "tokens": ["other", "half", "morning"], "outcome": null, "taken_unasked": false}}
  prose end: ns to chopping wood, the ax biting deep with each strike. The rhythmic sound fills the hall like a heartbeat, steady and strong. You watch her for a moment, considering your next move as you try to figure out how you'll come up with another 10 silvers by dawn.

## T54 (14.13s, 0 calls)
  > I turn to the old clerk and say: I only wanted to pay the guild, please write down what I owe and what I have paid.
  at the Chandlers' Guild hall | gold 40 | hp 19 | energy 12 | +6 min
  new rows: {"npcs": {"rows": ["#17 Ermengarde"], "writes": [9, 36, 37, 43]}}
  coins in prose: ['three silvers']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "F"]}
  · {"decision": "name_is_a_person", "name": "Ermengarde", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": 11, "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  · {"decision": "checked_offer_kept", "title": "Pay Guild Fees", "keyword_verdict": "no_offer_in_exchange"}
  · {"decision": "pencilled_in", "names": ["Ermengarde"]}
  · {"decision": "sketch_identity_asked", "name": "Ermengarde", "asked": ["O", "N", "G", "F", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Ermengarde", "evidence": "conversation"}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Ermengarde", "pronouns": "she"}]}
  prose end: scratching on the vellum. "Sign here to acknowledge you've been charged." You step closer, peering over her shoulder at the entry being made about you. Eleven more silvers... it's not much but with each payment brings you a little deeper into this guild's web.

## T55 (23.02s, 0 calls)
  > I count five silver onto the counter in front of Ermengarde and say that is a payment toward the debt.
  at the Chandlers' Guild hall | gold 40 | hp 19 | energy 12 | +6 min
  new rows: {"quest_steps": {"rows": ["#7 Candle-dipping"], "writes": [45, 46]}, "gm_events": {"rows": ["#9 Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present."], "writes": [36]}}
  coins in prose: ['five silver', 'Five silvers', '5 silvers', 'Five silvers', 'Five silvers']
  die skill:'Perception'DELTA +2 ban skill_gain small 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "N", "F"]}
  · {"decision": "name_is_a_person", "name": "Linnet Halloway", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "coin", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Thornhallow, outside the Chandlers' Guild hall", "confirm": "Yes, you are"}
  · {"decision": "settled", "detail": {"source": "prose_paid", "gold_delta": -0.05, "offer": 0.05, "model": null, "money_delta": -500}}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end:  in the loft." She glances up at you with an appraising look. You pause, considering. The silver is good, but sleeping here means no place to call your own and more of Ermengarde [[Q]]'s sharp tongue. Still... "Five silvers a day," you repeat, mulling it over.

## T56 (18.02s, 0 calls)
  > I accept the candle-dipping work and ask Ermengarde when I would be paid for it.
  at the Chandlers' Guild hall | gold 40 | hp 19 | energy 13 | +5 min
  coins in prose: ['two silvers']
  die check:persuasion check failure 1d20=1
  · {"decision": "absent_not_an_opponent", "names": ["Woman 1", "Bryony", "Benedict"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "N", "F"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Ermengarde", "why": "Most people in Ermengarde's position would agree to pay you for the candle-dipping work,
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "figure_is_listed_person", "hint": "a young woman"}
  prose end: atch you finish." With that settled, you thank Ermengarde [[Q]] and head over to introduce yourself to Gisela [[N]], who's already hard at the task of dipping candles. She seems friendly and willing to show you the ropes as you get started on your first batch.

## T57 (9.76s, 0 calls)
  > I sit on a bench by the wall and eat my loaf of bread.
  at the Chandlers' Guild hall | gold 40 | hp 19 | energy 15 | +20 min
  die skill:general skill_gain trivial 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "Q", "F"]}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "sketch_faded", "name": "Benedict", "made": 53, "unmentioned_turns": 5}
  prose end: ood with a small knife. Ermengarde [[Q]] leans against the far wall, her eyes closed in apparent slumber. After finishing your bread, you stand up and stretch. The guild hall is dimly lit by flickering torchlight that casts dancing shadows on the stone floors.

## T58 (11.32s, 0 calls)
  > I thank Ermengarde, leave the guild hall and walk out of town along the old King's Road toward the Greywold hills to look for a wolf or other beast.
  at the Chandlers' Guild hall -> old King's Road | gold 40 | hp 19 | energy 15 | +6 min
  new rows: {"npcs": {"rows": ["#18 Figure 2", "#19 Figure 3"], "writes": [14, 15, 16, 19, 20, 43]}, "locations": {"rows": ["#9 old King's Road"], "writes": [10, 11]}}
  die check:perception check success 1d20=14
  · {"decision": "absent_not_an_opponent", "names": ["Woman 1", "Bryony"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "N", "F"]}
  · {"decision": "name_is_a_place", "name": "Thane", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "breeze", "by": "ask", "first": false, "check": null}
  · {"decision": "new_place_outside_town", "place": "old King's Road", "town": "Thornhallow"}
  · {"decision": "unnamed_figure_numbered", "name": "Figure 2", "code": "R", "attitude": "neutral", "by": "record"}
  · {"decision": "unnamed_figure_numbered", "name": "Figure 3", "code": "S", "attitude": "neutral", "by": "record"}
  · {"decision": "pencilled_in", "names": ["Figure 2", "Figure 3"]}
  prose end: along the crest of a ridge. Your hand strays to the staff at your side. As you watch, two figures detach from the beast and descend toward you - not one wolf but two, cloaked and hooded. They draw closer and slow as they see you. One raises a hand in greeting.

## T59 (13.41s, 0 calls)
  > I stop on the road, keep my broom ready, and call out to the two cloaked figures to ask who they are.
  at old King's Road | gold 40 | hp 19 | energy 15 | +5 min
  die check:persuasion check success 1d20=11
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["R", "S"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most ordinary people would feel it's appropriate to greet and question strangers on the road, as long as 
  · {"decision": "quote_said_by_a_person", "quote": "Who are you?"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside old King's Road, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_one_here", "kind": "figure", "names": ["Figure 2", "Figure 3"]}
  · {"decision": "sketch_confirmed", "name": "Figure 2", "evidence": "ops"}
  · {"decision": "sketch_confirmed", "name": "Figure 3", "evidence": "ops"}
  prose end: in hand, and call out to the cloaked figures. "Who are you?" You ask. The figures turn towards you. The one called Gisela [[N]] steps forward, setting her axe aside. She squints at you with a weathered look. "Who are you and what are you doing here?" she asks.

## T60 (11.64s, 0 calls)
  > I tell Gisela I am Wren, a hedge-mage's apprentice hunting for a wolf or beast in these hills, and ask if she has seen one.
  at old King's Road | gold 40 | hp 19 | energy 15 | +5 min
  die check:persuasion check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "R", "S"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "Gisela is a woodcutter, busy with her work. She has not seen a wolf or beast, but is curious
  · {"decision": "stays_as_shown", "place": "old King's Road", "status": "not_travel"}
  prose end: ] shakes her head. "No sign of anything like that, mage-apprentice. But we've found something else. Care to take a look?" She gestures to the ground where the other figures are hunched over. You see what looks like a large metal object half-buried in the dirt.

## T61 (12.86s, 0 calls)
  > I call Candlelight and kneel to look closely at the metal object in the dirt for any old script.
  at old King's Road | gold 40 | hp 19 | energy 14 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "R", "S"]}
  · {"decision": "name_is_a_person", "name": "Bennet Jessop", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside old King's Road, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end: You kneel down beside the metal object, calling up a mote of Candlelight to examine it closely. It appears to be an old coin, heavily worn but still bearing some traces of an inscription in an unknown language.

## T62 (13.53s, 0 calls)
  > I use my Old Script skill to try to read the inscription on the coin, then pick the coin up.
  at old King's Road | gold 40 -> 41 | hp 19 | energy 12 | +15 min
  new rows: {"quest_steps": {"rows": ["#8 Read inscription, picked up coin"], "writes": [39, 40]}}
  die check:investigation check partial 1d20=7
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "R", "S"]}
  · {"decision": "quote_not_said_by_a_person", "quote": "For valor in the King's Road quake, 27 years past."}
  · {"decision": "stays_as_shown", "place": "old King's Road", "status": "not_travel"}
  · {"decision": "quote_seeds_no_one", "quote": "For valor in the King's Road quake, 27 years past."}
  prose end: eeds now a part of your own journey. Continuing along King's Road [[L9]], you tread lightly on the old stones, your footsteps echoing in the night silence. The path ahead seems to stretch endlessly into the darkness, inviting further exploration and discovery.

## T63 (18.86s, 0 calls)
  > I leave the road and climb into the Greywold hills toward #L4, the old ruins, looking for any beast tracks.
  at old King's Road -> Ruins | gold 41 | hp 19 | energy 10 | +10 min
  new rows: {"npcs": {"rows": ["#20 Hubert Woodall"], "writes": [11, 18, 20, 46]}, "gm_events": {"rows": ["#10 Rumors thicken away from the player; loyalties may shift before the next meeting."], "writes": [37]}}
  die skill:general skill_gain trivial 1=1
  die check:perception check partial 1d20=8
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "R", "S"]}
  · {"decision": "name_is_a_person", "name": "Hubert Woodall", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "eye", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "rise", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "step", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_disagrees", "destination": "Ruins", "answer": "outside old King's Road, on the road or in the wilds"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "filed_at_player_place", "code": "T", "name": "Hubert Woodall", "was": 5, "now": 8, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Hubert Woodall"]}
  prose end: y do not move or speak. Your skin prickles with unease but also excitement at this potential lead. You cautiously approach the watcher, calling out again, "I mean no harm. I'm searching for any signs of beast activity near these ruins. Have you seen anything?"

## T64 (8.13s, 0 calls)
  > I stay still, hold my broom across my body and say clearly to the hooded figure: who are you, and are you the thing that has been prowling these ruins?
  at Ruins | gold 41 | hp 19 | energy 10 | +6 min
  · {"decision": "attack_target_unknown_noun", "noun": "figure", "minted": false, "target": null, "not_the_lines": null}
  · {"decision": "quote_said_by_a_person", "quote": "I am a collector of lost knowledge. These ruins hold secrets that I seek."}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "not_travel"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "sketch_identity_asked", "name": "Hubert Woodall", "asked": ["N"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Hubert Woodall", "evidence": "locations.keeper_npc_id"}
  prose end: . Then you ask clearly, "Who are you, and have you been prowling these ruins?" The figure's head tilts slightly as if considering whether to answer. Finally it speaks in an even voice, "I am a collector of lost knowledge. These ruins hold secrets that I seek."

## T65 (16.53s, 0 calls)
  > I lower my broom a little and ask the collector whether he has seen any wolves or other beasts nesting among these ruins.
  at Ruins | gold 41 | hp 19 | energy 10 | +5 min
  new rows: {"npcs": {"rows": ["#21 Finnian Sallow"], "writes": [6, 12, 15, 21, 43]}}
  die skill:BAND skill_gain small 1=1
  die check:persuasion check success 1d20=16
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["T", "N"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few might find the request odd or suspicious, but most are too busy to pay attention."}
  · {"decision": "name_is_a_person", "name": "Finnian Sallow", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "inch", "by": "ask", "first": false, "check": null}
  · {"decision": "refused", "item": {"name": "ITEM", "tokens": ["item"], "outcome": null, "taken_unasked": false}}
  · {"decision": "figure_is_known_person", "hint": "a tall man"}
  · {"decision": "filed_at_player_place", "code": "U", "name": "Finnian Sallow", "was": 7, "now": 8, "why": "filed_here"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["Finnian Sallow"]}
  prose end:  stone walls and piles of rubble as if expecting to see some confirmation. There are no signs though - just empty darkness. "Nothing's tried the shop yet," Hubert continues, "though we keep a fire going inside and the doors barred. Best not to draw attention."

## T66 (13.14s, 0 calls)
  > I call Candlelight and search the rubble of the ruins for fresh paw tracks and a den.
  at Ruins | gold 41 | hp 19 | energy 9 | +15 min
  die check:perception check success 1d20=19
  · {"decision": "absent_not_an_opponent", "names": ["Finnian Sallow"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["T", "N"]}
  · {"decision": "place_bound_by_reference", "code": "L4", "place": "Greywold Ruins", "words": "the ruins"}
  · {"decision": "name_is_a_person", "name": "Hubert", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "not_travel"}
  prose end: ouldn't put it past the thing to have just moved on deeper into the ruins rather than leave." "Could be dangerous to go poking about in its den," Hubert warns, eyeing you. "Though from the look of those tracks it's been a while since it was last back there..."

## T67 (13.63s, 0 calls)
  > I follow the big paw tracks deeper into the ruins, step by step, with my broom ready and Candlelight lit.
  at Ruins | gold 41 | hp 19 | energy 7 | +6 min
  die skill:survival skill_gain small 1=1
  die check:survival check partial 1d20=7
  · {"decision": "absent_not_an_opponent", "names": ["Finnian Sallow"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "T"]}
  · {"decision": "name_is_a_person", "name": "Roderick", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "corner", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_a_figure", "kind": "shape", "by": "ask", "first": true, "check": true}
  · {"decision": "figure_not_hostile", "kind": "shape"}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: 's brightness to peer into the shadows. After a tense moment, no further movement is detected. Continuing onward, you can't shake the feeling that someone or something watches from the darkness – but who or what could be lurking in these deserted ruins [[L8]]?

## T68 (13.32s, 0 calls)
  > I creep up to the pillar where the dark shape vanished and shine my Candlelight behind it.
  at Ruins | gold 41 | hp 19 | energy 6 | +6 min
  die check:stealth check success 1d20=20
  · {"decision": "absent_not_an_opponent", "names": ["Finnian Sallow"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "T"]}
  · {"decision": "stays_as_shown", "place": "Ruins", "status": "not_travel"}
  prose end: d light shows fresh boot prints on the flagstones, leading into the shadows of the ruins [[L8]]. Gisela [[N]] looks over at you, curious. "You're being awfully quiet for a mage's apprentice," she remarks with a smirk as she goes back to cleaning her axe blade.

## T69 (18.02s, 0 calls)
  > I ask @N why she keeps turning up wherever I go, and whether she knows where the direwolf's den is.
  at Ruins -> Deeper Into Ruins | gold 41 | hp 19 | energy 6 | +5 min
  die skill:general skill_gain small 1=1
  die check:persuasion check success 1d20=11
  · {"decision": "absent_not_an_opponent", "names": ["Finnian Sallow"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "T"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "Gisela is curious about the direwolf and wants to help, despite her loyalty to her own tasks
  · {"decision": "noun_is_no_figure", "kind": "voice", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "pace", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Outside Thornhallow, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end: oft breathing of the night forest surrounds you as you reach out with your mind to sense any nearby presences - human or animal. "Ah." A voice startles you. You open your eyes and see Gisela [[N]] standing a few paces away. "I seem to turn up wherever you go."

## T70 (16.72s, 0 calls)
  > !wait 240 sleep
  at Deeper Into Ruins | gold 41 | hp 20 (+1) | energy 15 | +240 min
  new rows: {"quests": {"rows": ["#6 cut firewood"], "writes": [36, 37, 38, 44]}, "quest_steps": {"rows": ["#9 cut firewood"], "writes": [39]}}
  · {"decision": "name_is_a_person", "name": "Jasper Cotter", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "split", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "ear", "by": "ask", "first": false, "check": null}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "The wood is damp and resists the bite of your blade at first, but soon splits apart under your strokes."}
  · {"decision": "checked_offer_kept", "title": "cut firewood", "keyword_verdict": "no_offer_in_exchange"}
  · {"decision": "sketch_faded", "name": "Finnian Sallow", "made": 66, "unmentioned_turns": 5}
  prose end: nd the temperature warms. You pause for a drink from your waterskin before resuming your work. Gisela [[N]] suddenly stops chopping and looks at you intently. "I have an important question to ask you," she says seriously. "What's your name, mage's apprentice?"

## T71 (11.7s, 0 calls)
  > I tell @N my name is Wren, she already knows it, and I put down the axe: I will not cut firewood today, I am hunting the direwolf. Where do I find it?
  at Deeper Into Ruins | gold 41 | hp 20 | energy 15 | +6 min
  new rows: {"gm_events": {"rows": ["#11 Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present."], "writes": [22]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_one_here", "kind": "figure", "names": ["Figure 1"]}
  prose end: N]] nods slowly, seeming to accept your answer. The unnamed figure finally speaks up. "Testing yourself is always wise," they say quietly. "But remember that wisdom comes in many forms. Perhaps you could test your wisdom as well as your strength on this hunt?"

## T72 (10.35s, 0 calls)
  > I shoulder my broom and climb out of the ruins up into the Greywold hills, following the big paw prints toward the direwolf's den.
  at Deeper Into Ruins -> Greywold Ruins | gold 41 | hp 20 | energy 14 | +10 min
  new rows: {"npcs": {"rows": ["#22 Dafydd"], "writes": [13, 14, 17, 36]}}
  die check:athletics check critical_failure 1d20=2
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "M"]}
  · {"decision": "place_left_not_destination", "place": "Ruins"}
  · {"decision": "place_left_not_destination", "place": "Ruins"}
  · {"decision": "name_is_a_person", "name": "Dunstan Hobb", "by": "ask", "why": "op_person"}
  · {"decision": "place_left_not_destination", "place": "Ruins"}
  · {"decision": "common_noun_names_known_place", "noun": "greywold", "place": "Greywold Ruins"}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "outside Deeper Into Ruins, on the road or in the wilds", "destination": "Greywold Ruins"}
  · {"decision": "pencilled_in", "names": ["Dafydd"]}
  prose end: or a moment outside the dwelling. The snow falls softly and you listen for any signs of life within. After a short time, the door creaks open and an older woodcutter with grizzled hair emerges from within. "You there," he calls out. "What brings you this way?"

## T73 (12.13s, 0 calls)
  > I greet the woodcutter, say I am following direwolf tracks, and ask if he has seen the beast or where it lairs.
  at Greywold Ruins | gold 41 | hp 20 | energy 14 | +5 min
  die check:persuasion check success 1d20=12
  · {"decision": "absent_not_an_opponent", "names": ["Dafydd"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Gisela", "why": "Most woodcutters would be too busy working to pay attention to direwolf tracks."}
  · {"decision": "name_is_a_person", "name": "woodcutter", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Greywold Ruins", "status": "unresolved"}
  · {"decision": "same_name_other_spelling", "name": "Greywold Ruins.", "known": "Greywold Ruins"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: atures. They may have dens anywhere - under cliffs, in caves... It's best not to hunt them alone. You'll need quick wits and a keen eye." She pauses, studying your face. "Why do you seek out such beasts anyway? An apprentice like yourself has better pursuits."

## T74 (24.54s, 0 calls)
  > I thank Gisela and head east along the hills with Candlelight lit, watching for the direwolf.
  at Greywold Ruins -> Outside Thornhallow | gold 41 | hp 20 | energy 13 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "move_from_prose", "destination": "Outside Thornhallow", "kind": "outside", "status": "unresolved"}
  prose end: along the base of the hill, Candlelight's soft glow lighting your way. The paw-pressed snow crunches underfoot as you walk, casting shifting shadows on the rock walls. Your eyes are drawn to a faint set of clawed foot marks that lead up into the rocky terrain.

## T75 (12.34s, 0 calls)
  > I climb after the clawed foot marks into the rocks, my broom ready, and look for the direwolf.
  at Outside Thornhallow | gold 41 | hp 20 | energy 10 | +10 min
  die item:pace item_count small 1=1
  die check:perception check critical_success 1d20=20
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "noun_is_no_figure", "kind": "growl", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "rise", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "head", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Outside Thornhallow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "refused", "item": {"name": "pace", "tokens": ["pace"], "outcome": "gain", "taken_unasked": true}}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "payout_refused", "quest": "skilled labor", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  prose end: olf growls low in its throat, hackles rising. You fumble for your broom, heart pounding as you try to remember what Master Pottle said about direwolves - something about not making direct eye contact? You lock gazes with the beast and slowly lift your broom...

## T76 (15.75s, 0 calls)
  > I swing my broom at the direwolf's snout.
  at Outside Thornhallow | gold 41 | hp 18 (-2) | energy 10 | +6 min
  die player.health_delta 1d4=-2 (turn_bands)
  die skill:melee skill_gain small 1=1
  die check:melee check success 1d20=15
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "noun_is_no_figure", "kind": "human", "by": "ask", "first": true, "check": false}
  prose end: as if gesturing for you to stay back. The other reaches into a pouch at their waist and retrieves what looks like a small vial of clear liquid. The scene is tense, with the direwolf's focus still on you and the two humans cautiously approaching from behind it.

## T77 (13.73s, 0 calls)
  > I step back and swing my broom at the direwolf's side again, then watch what the two figures do.
  at Outside Thornhallow | gold 41 | hp 18 | energy 9 | +6 min
  die check:melee check critical_success 1d20=20
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Outside Thornhallow, on the road or in the wilds", "confirm": "Yes"}
  · {"decision": "sketch_faded", "name": "Dafydd", "made": 73, "unmentioned_turns": 5}
  prose end: catch it just right and the blow connects solidly, sending the creature stumbling sideways into Gisela [[N]] who yelps in alarm. It recovers quickly though, shaking off the impact with a snarl and fixing you with an angry yellow eye as it circles around again.

## T78 (15.18s, 0 calls)
  > I lunge and strike at the direwolf's throat with the broom, putting all my weight behind it.
  at Outside Thornhallow | gold 41 | hp 18 | energy 7 | +6 min
  die check:melee check success 1d20=18
  · {"decision": "attack_found", "target": {"code": "N", "name": "Gisela"}, "source": "trigger", "skill": "", "people": []}
  · {"decision": "combat_follows_attack_check", "code": "N", "check_outcome": "success", "was": "miss", "now": "hit", "damage": 4}
  · {"decision": "offer_names_no_task", "title": "subdue direwolf", "line": "Well, I suppose I should thank you for that. Though I daresay your aim could use some work. By the look on your face, I'm guessing this is your fir
  · {"decision": "name_is_a_person", "name": "Brida Elwood", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "at Ruins", "confirm": "Yes, you are"}
  · {"decision": "same_name_other_spelling", "name": "Deeper Into Ruins.", "known": "Deeper Into Ruins"}
  prose end: ome work." She picks up the fallen axe and starts trudging towards the ruins again. You fall into step beside her. "By the look on your face," Gisela [[N]] continues after a moment's silence, "I'm guessing this is your first time fighting something like that?"

## T79 (12.17s, 0 calls)
  > I head back down to #L1 Thornhallow.
  at Outside Thornhallow -> Thornhallow | gold 41 | hp 18 | energy 7 | +6 min
  new rows: {"gm_events": {"rows": ["#12 Off-screen movement continues around Thornhallow."], "writes": [27]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "place_bound_by_reference", "code": "L1", "place": "Thornhallow", "words": "Thornhallow", "how": "typed_and_named"}
  · {"decision": "noun_is_no_figure", "kind": "woodcutter", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Good morning,"}
  · {"decision": "player_code_travel", "code": "L1", "destination": "Thornhallow", "replaced": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "at Deeper Into Ruins", "confirm": "Yes, you are"}
  prose end: rks at Deeper Into Ruins [[L5]] and has been friendly since you arrived. She nods, a small smile on her lips as she adjusts the pack on her shoulder. "Aye, there's always more trees that need the axe. But I'm glad to see you made it through the night alright."

## T80 (14.47s, 0 calls)
  > I find @A and offer him my dried meat for two silver.
  at Thornhallow | gold 41 | hp 18 | energy 6 | +6 min
  new rows: {"npcs": {"rows": ["#23 Server 1"], "writes": [10, 11, 36, 40]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N"]}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "unnamed_figure_numbered", "name": "Server 1", "code": "U", "attitude": "neutral", "by": "record"}
  · {"decision": "pencilled_in", "names": ["Server 1"]}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Server 1", "pronouns": "he"}]}
  prose end: ir tasks - a baker kneading dough at one end of the counter, while a server busily sets out place settings for the morning rush. The clatter of pots and pans and the sizzling of food cooking on the stovetop create a lively soundtrack to the kitchen's activity.

## T81 (15.73s, 0 calls)
  > I hold out the dried meat to @A and say: two silver, Roger, and it is yours.
  at Thornhallow | gold 41 | hp 18 | energy 6 | +6 min
  coins in prose: ['Two silver', 'Two silvers']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "N", "U"]}
  · {"decision": "speech_said_before_dropped", "lines": ["\"I see you've managed to find some food,\" he says with a smirk as he gestures towards your sack of supplies.", "\"If you're looking for work, I could use an extra s
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: chopping vegetables. You hold out the dried meat to him and say: "Two silver, Roger, and it is yours." He eyes the meat, then holds up two fingers. "Alright, deal. Two silvers it is." Roger [[A]] takes the dried meat from your hand and pockets it with a smile.

## T82 (19.3s, 0 calls)
  > I wait for @A to count out my two silver, and ask him to hand it over.
  at Thornhallow | gold 41 | hp 18 | energy 6 | +15 min
  coins in prose: ['Ten silver', 'Ten silvers']
  die check:persuasion check failure 1d20=1
  · {"decision": "absent_not_an_opponent", "names": ["Patron 1", "Patron 2"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "N", "U"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Roger", "why": "Roger is busy and may not have time to count out change, but he might do it if politely asked
  · {"decision": "name_is_a_person", "name": "Anselm Ridley", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "same_name_other_spelling", "name": "The Shears and Wheel.", "known": "The Shears and Wheel"}
  · {"decision": "settled", "detail": {"source": "offer_unanswered", "offer": 0.02, "gold_delta": 0, "money_delta": 0}}
  prose end: Roger [[A]] says, nodding towards the pile of coppers. "Ten silver in all." You reach out and take the stack of coins, feeling their weight in your palm. Ten silvers for a day's work – not bad. But it's still hard to shake this sense that there should be more.

## T83 (19.48s, 0 calls)
  > I ask @A where the notice board is, and go look at it.
  at Thornhallow | gold 41 | hp 18 | energy 7 | +5 min
  die check:persuasion check success 1d20=13
  · {"decision": "absent_not_an_opponent", "names": ["Patron 1", "Patron 2"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["A", "N", "U"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "dismissive", "person": "Roger", "why": "Roger may know where the notice board is, and is generally helpful."}
  · {"decision": "name_is_a_person", "name": "landlord's son", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: uare, bathed in morning sunlight that filters through the leafy boughs of tall oaks. A few other people browse the notices as well before heading off on their errands. The air is cool and fresh, filled with birdsong and distant laughter from the nearby tavern.

## T84 (22.13s, 0 calls)
  > I accept the work on the slip, head to #L2, and ask the barkeep @B what the pay is.
  at Thornhallow | gold 41 | hp 18 | energy 7 | +5 min
  new rows: {"npcs": {"rows": ["#24 Server 2"], "writes": [12, 13, 35, 37]}}
  die check:persuasion check failure 1d20=2
  die unnamed_count:server figure_count server 1d4+1=2
  · {"decision": "absent_not_an_opponent", "names": ["Patron 1", "Patron 2"], "named_in_line": false}
  · {"decision": "attack_target_absent", "absent": {"code": "B", "name": "Arnulf Bramley", "place": "L2", "place_name": "The Shears and Wheel", "dead": false}, "rolled": false, "not_the_lines": null}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most workers are eager for any job opportunity, but a few may turn it down if the pay or conditions aren'
  · {"decision": "place_bound_by_reference", "code": "L2", "place": "The Shears and Wheel", "words": "The Shears and Wheel"}
  · {"decision": "noun_is_no_figure", "kind": "tapster", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "voice", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Nice to see you again,"}
  · {"decision": "player_code_travel", "code": "L2", "destination": "The Shears and Wheel", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  · {"decision": "figure_is_one_here", "kind": "patron", "names": ["Patron 1", "Patron 2"]}
  · {"decision": "unnamed_figure_numbered", "name": "Server 2", "code": "X", "attitude": "neutral", "by": "record"}
  · {"decision": "unstated_count_rolled", "kind": "server", "phrase": "servers", "notation": "1d4+1", "rolls": [1], "count": 2, "prose_written": true, "summary_written": false}
  · {"decision": "pencilled_in", "names": ["Server 2"]}
  · {"decision": "sketch_confirmed", "name": "Server 1", "evidence": "ops"}
  prose end: y through the tavern. "Nice to see you again," Nicol Skinner says, nodding in greeting as he finishes polishing a mug and sets it on a shelf behind him. "Just starting your day already? I can pour you some porridge if you like - it's still warm from the fire."

## T85 (9.69s, 0 calls)
  > I walk into The Shears and Wheel at #L2 and ask @B directly: what does the skilled labor pay?
  at Thornhallow | gold 41 | hp 18 | energy 7 | +5 min
  die check:persuasion check success 1d20=11
  · {"decision": "attack_target_absent", "absent": {"code": "B", "name": "Arnulf Bramley", "place": "L2", "place_name": "The Shears and Wheel", "dead": false}, "rolled": false, "not_the_lines": null}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most skilled workers would be curious and happy to discuss their pay with a newcomer."}
  · {"decision": "place_bound_by_reference", "code": "L2", "place": "The Shears and Wheel", "words": "The Shears and Wheel", "how": "typed_and_named"}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "The Shears and Wheel"}
  · {"decision": "player_code_travel", "code": "L2", "destination": "The Shears and Wheel", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  prose end: ver you. The chatter of patrons greets your ears as you scan the room. In the corner, a barkeep not yet on shift notices your gaze and approaches. "Can I help you?" he asks with a neutral tone, eyeing you appraisingly. "Looking for work or just in for an ale?"

## T86 (11.52s, 0 calls)
  > I go to #L2.
  at Thornhallow | gold 41 | hp 18 | energy 7 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "U", "A", "C"]}
  · {"decision": "place_bound_by_reference", "code": "L2", "place": "The Shears and Wheel", "words": "The Shears and Wheel"}
  · {"decision": "quote_said_by_a_person", "quote": "Ah, good morrow,"}
  · {"decision": "player_code_travel", "code": "L2", "destination": "The Shears and Wheel", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  prose end: th a nod. "Come on in out of the chill." The air is thick with the scents of smoke and stewed meats. Behind the bar, a younger man is wiping down glasses. "Good to have you," says the barrel-chested man. "We've got fresh bread and ale. What can I get for you?"

## T87 (11.63s, 0 calls)
  > I step through the doorway into the tavern and sit at the bar, asking for a mug of small ale.
  at Thornhallow | gold 41 | hp 18 | energy 7 | +6 min
  new rows: {"npcs": {"rows": ["#25 Edith"], "writes": [10, 13, 36, 38]}}
  die check:persuasion check success 1d20=11
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["N", "U", "A", "C"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "Entering a tavern and ordering a drink is a normal, everyday action that most people would not refuse."}
  · {"decision": "name_is_a_person", "name": "Godfrey Tully", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_enter", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  · {"decision": "name_fits_the_sex_shown", "given": "Godfrey Tully", "drawn": "Edith", "shown": "female"}
  · {"decision": "figure_is_one_here", "kind": "server", "names": ["Server 1", "Server 2"]}
  · {"decision": "pencilled_in", "names": ["Edith"]}
  · {"decision": "sketch_confirmed", "name": "Server 2", "evidence": "ops"}
  prose end:  tankards of dark ale in front of your neighbors. "Small ale." The server, an older woman with graying hair tied back, fills a mug from a cask behind her and sets it before you. She eyes you appraisingly. "New in town?" she asks, wiping her hands on her apron.

## T88 (11.54s, 0 calls)
  > I pay Edith two copper for the ale and drink it.
  at Thornhallow | gold 41 | hp 18 | energy 9 | +20 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Y", "N", "U", "A"]}
  · {"decision": "quote_said_by_a_person", "quote": "Another?"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "player_paid_outright", "amount": 0.0002, "line": "I pay Edith two copper for the ale and drink it."}
  · {"decision": "band_label_not_an_item", "item": "small", "label": "small"}
  · {"decision": "loss_not_shown", "gold_delta": -0.0002, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "player_paid", "gold_delta": 0, "offer": 0.0002, "model": null, "money_delta": 0, "stated_delta": -0.0002, "changed_by": "loss_not_shown"}}
  · {"decision": "figure_is_one_here", "kind": "server", "names": ["Server 1", "Server 2"]}
  · {"decision": "sketch_identity_asked", "name": "Edith", "asked": ["Q", "N", "G", "F", "B"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Edith", "evidence": "prose_code"}
  prose end: l of smoke lingers in the air from last night's hearth fires. The sounds of clinking crockery and low conversation provide a backdrop to your own thoughts. "Another?" Edith [[Y]] asks, her hand resting on your empty tankard. "Or perhaps some bread and cheese?"

## T89 (10.06s, 0 calls)
  > I ask Edith [[Y]] whether the skilled labor slip still stands, and what the pay is.
  at Thornhallow | gold 41 | hp 18 | energy 9 | +5 min
  coins in prose: ['Eight gold']
  die check:persuasion check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Y", "N", "U", "A"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Edith", "why": "Edith is eager to provide details about the labor and pay."}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": 8, "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  prose end: " she confirms. "And room and board while you're here." Edith [[Y]] waits patiently, used to weighing offers from travelers like yourself. In her experience, most are just passing through, but every now and then a skilled worker sticks around for a bit longer.

## T90 (30.72s, 0 calls)
  > I tell Edith I accept the skilled labor for eight gold, and ask what I must do first.
  at Thornhallow | gold 41 | hp 18 | energy 10 | +5 min
  new rows: {"locations": {"rows": ["#10 The Stables"], "writes": [13, 14]}}
  coins in prose: ['eight gold']
  die item:wage agreement item_count trivial 1=1
  die check:persuasion check partial 1d20=8
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Y", "N", "U", "A"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "patient", "person": "Edith", "why": "Edith is eager to secure skilled labor for her wine shop and will likely accept your offer."}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  · {"decision": "not_a_thing", "item": "wage agreement", "why": "the grant names a job, wage or deal"}
  · {"decision": "loss_not_shown", "gold_delta": -8, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "refused", "item": {"name": "wage agreement", "tokens": ["wage", "agreement"], "outcome": "gain", "taken_unasked": false}}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "stated", "gold_delta": 0, "offer": null, "model": -8, "money_delta": 0, "stated_delta": -8, "changed_by": "loss_not_shown"}}
  prose end: er. "Very well then. First thing to do is clean out the stables." Edith [[Y]] gestures towards the back door with a tilt of her head. "The stables are this way. The place could use a good cleaning after last night's revels." She hands you a broom and a bucket.

## T91 (28.16s, 0 calls)
  > I go to the stables and sweep them out with my broom.
  at Thornhallow | gold 41 | hp 18 | energy 7 | +25 min
  new rows: {"npcs": {"rows": ["#26 Barnabus"], "writes": [11, 17, 37]}}
  die check:athletics check failure 1d20=4
  · {"decision": "name_is_a_person", "name": "Barnabus", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "still in Thornhallow", "destination": "The Shears and Wheel"}
  · {"decision": "placed_in_scene", "name": "Barnabus", "unknown_place": "Thornhallow Stables", "place": "The Shears and Wheel"}
  · {"decision": "filed_at_player_place", "code": "Z", "name": "Barnabus", "was": 2, "now": 1, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Barnabus"]}
  prose end: h your broom in hand. "Ah, a customer at last," remarks the stablemaster, looking up from his work as you enter. He's a gruff but competent-looking fellow who seems to take your presence in stride. "Welcome to Thornhallow Stables. What can I do for you today?"

## T92 (11.14s, 0 calls)
  > I tell Barnabus @Edith sent me to muck out the stables, and I start sweeping.
  at Thornhallow -> The Stables | gold 41 | hp 18 | energy 4 | +25 min
  die check:athletics check success 1d20=17
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Z"]}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "The Stables"}
  · {"decision": "where_ended_not_confirmed", "answer": "at The Stables", "confirm": "Yes, you are"}
  · {"decision": "sketch_identity_asked", "name": "Barnabus", "asked": ["Y", "N", "A"], "answer": "N", "raw": "{'answer': 'N'}"}
  · {"decision": "sketch_merge_unsupported", "name": "Barnabus", "answered": "N", "known": "Gisela"}
  · {"decision": "sketch_confirmed", "name": "Barnabus", "evidence": "ops"}
  prose end: shing the straw into piles that Barnabus [[Z]] shovels out into the yard. After a time, Barnabus [[Z]] sets down his ledger and comes over to help. "You know," he says as he tosses a shovel to you, "if you're looking for steady work, I could use another hand."

## T93 (11.26s, 0 calls)
  > I go back to #L2 and tell Edith the stables are swept, and ask for my eight gold.
  at The Stables | gold 41 | hp 18 | energy 4 | +5 min
  die item:eight gold item_count trivial 1=1
  die check:persuasion check success 1d20=19
  · {"decision": "attack_target_absent", "absent": {"code": "Y", "name": "Edith", "place": "L1", "place_name": "Thornhallow", "dead": false}, "rolled": false, "not_the_lines": null}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "The player's request is reasonable and expected, as the character has completed the task of sweeping the s
  · {"decision": "speech_said_before_dropped", "lines": ["\"Ah, so the rumors were true,\" she says with a smirk as you approach."]}
  · {"decision": "place_bound_by_reference", "code": "L2", "place": "The Shears and Wheel", "words": "The Shears and Wheel"}
  · {"decision": "player_code_travel", "code": "L2", "destination": "The Shears and Wheel", "replaced": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "in Thornhallow, outside The Stables", "confirm": "Yes."}
  · {"decision": "gain_without_coin_dropped", "stated": 8, "why": "the prose shows no coin reaching the player"}
  · {"decision": "refused", "item": {"name": "eight gold", "tokens": ["eight", "gold"], "outcome": "unshown_loss"}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null, "money_delta": 0}}
  prose end: You head back to the tavern and find Edith sitting alone at a table, nursing a mug of something. "You're seeking actual honest labor after all."

## T94 (10.18s, 0 calls)
  > I sit down across from Edith and say plainly: the stables are done, please pay me the eight gold we agreed.
  at The Stables | gold 41 -> 56 | hp 18 | energy 4 | +6 min
  coins in prose: ['eight gold', 'Eight gold']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Y", "Z"]}
  · {"decision": "offer_names_no_task", "title": "stables tidied", "line": "You've certainly kept yourself busy, I suppose I can't argue with a job well done. Eight gold it is then. Here you go then, Make sure to pay your ta
  · {"decision": "stays_as_shown", "place": "The Stables", "status": "not_travel"}
  · {"decision": "loss_not_shown", "gold_delta": -8, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "stated_mention", "gold_delta": 0, "offer": 8, "model": -8, "money_delta": 0, "stated_delta": -8, "changed_by": "loss_not_shown"}}
  · {"decision": "paid", "quest": "Q1", "action": "step_done", "paid": {"gold": 15, "xp": 25, "karma": 0, "items": [], "units": 1, "text": "+15 gold, +25 XP", "money_units": 150000, "settled": 15, "source": "parser"}, "quote
  prose end: done. Eight gold it is then." She reaches into a pouch at her belt and pulls out a handful of coins, laying them on the table between you with a clink. "Here you go then," she says as you reach for the pile. "Make sure to pay your taxes when you get a chance."

## T95 (12.79s, 0 calls)
  > I leave the tavern and go to #L3 the Chandlers' Guild hall.
  at The Stables -> the Chandlers' Guild hall | gold 56 | hp 18 | energy 4 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Z", "Y"]}
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "the Chandlers' Guild hall", "words": "the Chandlers' Guild hall", "how": "typed_and_named"}
  · {"decision": "noun_is_no_figure", "kind": "desk", "by": "ask", "first": false, "check": null}
  · {"decision": "player_code_travel", "code": "L3", "destination": "the Chandlers' Guild hall", "replaced": "#L3"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "outside Thornhallow, on the road or in the wilds", "destination": "the Chandlers' Guild hall"}
  · {"decision": "unshown_known_person_stays", "name": "Gisela", "place": "L1"}
  prose end:  some are hard at their studies, others chatting quietly amongst themselves. At the end of the row sits Gisela [[N]], an older mage with graying hair and a no-nonsense air about her. She glances up from her ledger as you approach. "Yes? What can I do for you?"

## T96 (12.27s, 0 calls)
  > I tell @Q Ermengarde I want to pay down Hesper's wax debt, and I put ten silver on her desk.
  at the Chandlers' Guild hall | gold 56 | hp 18 | energy 4 | +6 min
  coins in prose: ['ten silver']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "F"]}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  · {"decision": "settled", "detail": {"source": "prose_paid", "gold_delta": -0.1, "offer": 0.1, "model": null, "money_delta": -1000}}
  prose end: ttle bit helps." She dips a quill in ink and scratches something into a wax-sealed letter. "I'll mark this down for you. Come by tomorrow same time and we can talk about what else might be due from you. The Guild's always looking for good workers to train up."

## T97 (11.37s, 0 calls)
  > I open Hesper's grimoire and call Candlelight to read the oldest page with my Old Script.
  at the Chandlers' Guild hall | gold 56 | hp 18 | energy 2 | +15 min
  die check:investigation check partial 1d20=8
  · {"decision": "absent_not_an_opponent", "names": ["Woman 1", "Bryony"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "F"]}
  · {"decision": "stays_as_shown", "place": "the Chandlers' Guild hall", "status": "not_travel"}
  prose end: says, following your gaze to the tracks. "I wonder where they're going?" The ancient writing on the next page catches your eye. It seems to be instructions in Old Script - a recipe of some kind? You can just make out words like 'fire', 'bricks', and 'cooking'.

## T98 (18.7s, 0 calls)
  > I thank @Q Ermengarde, then tell @A in #L1 that I will sell him the dried meat tomorrow.
  at the Chandlers' Guild hall -> Thornhallow | gold 56 | hp 18 | energy 2 | +6 min
  inv - ['dried x1']
  die item:dried item_count small 1=1
  die skill:General Check skill_gain trivial 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q", "F"]}
  · {"decision": "place_bound_by_reference", "code": "L1", "place": "Thornhallow", "words": "Thornhallow"}
  · {"decision": "player_code_travel", "code": "L1", "destination": "Thornhallow", "replaced": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "player_code", "answer": "still in the Chandlers' Guild hall", "destination": "Thornhallow"}
  prose end:  floor. Racks of herbs hang from the ceiling, their fragrant leaves swaying gently in the breeze from the open door. Roger [[A]] nods curtly in acknowledgement of your promise before returning to his work, a large knife in hand as he begins jointing a chicken.

## T99 (20.72s, 0 calls)
  > !wait 360 sleep
  at Thornhallow | gold 56 | hp 20 (+2) | energy 16 | +360 min
  · {"decision": "speech_said_before_dropped", "lines": ["\"I've never seen anything like it before.\""]}
  prose end: utting board with a friendly smile. "And you have sharp eyes for it, don't you?" Wren blushes slightly at the compliment. "Well I've always had an interest in such things. But that's not why I came over actually. I was hoping to ask your opinion on something."

## T100 (8.27s, 0 calls)
  > I stay where I am in Thornhallow and look around the square, then check my purse.
  at Thornhallow | gold 56 | hp 20 | energy 16 | +6 min
  die check:perception check success 1d20=9
  · {"decision": "absent_not_an_opponent", "names": ["Roger", "Patron 1", "Patron 2", "Gisela", "Server 1", "Server 2"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["Q"]}
  · {"decision": "noun_is_no_figure", "kind": "type", "by": "ask", "first": true, "check": false}
  · {"decision": "quote_said_by_a_person", "quote": "Can I help you, friend?"}
  · {"decision": "stays_as_shown", "place": "Thornhallow", "status": "not_travel"}
  prose end: ions, nothing else to speak of. Enough to get by but not much in reserve. "Can I help you, friend?" comes a voice from behind. You turn to see Gisela [[N]], the woodcutter with a pile of chopped firewood at her feet. "Just passing through or looking for work?"

100 turns: median 12.9s mean 14.2s max 31.8s; model calls median 0.0
