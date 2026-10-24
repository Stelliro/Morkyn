
## T1 (16.05s, 0 calls)
  > I look the tallyman over and say I know I owe him, but I want to know exactly how much I owe.
  at Saltmarrow | gold 12 | hp 20 | energy 16 | +6 min
  · {"decision": "noun_is_no_figure", "kind": "tallyman", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "figure_is_one_here", "kind": "person", "names": ["Person 1"]}
  · {"decision": "sketch_confirmed", "name": "Person 1", "evidence": "ops"}
  prose end: eps careful count. You see the person [[A]], the unnamed message runner, working at a nearby table, his eyes flicking back and forth over a ledger. You catch his eye and he looks up, recognizing you. He stands and approaches. He says, "I have a tally for you."

## T2 (11.62s, 0 calls)
  > I tell @A to read me the tally, and say I'll pay what I can from twelve gold.
  at Saltmarrow | gold 12 | hp 20 | energy 16 | +15 min
  new rows: {"npcs": {"rows": ["#2 Lettice Orme"], "writes": [13, 33]}}
  coins in prose: ['twelve pieces', 'Twelve gold', 'Twelve pieces', 'twelve gold']
  · {"decision": "routine_read_no_check", "line": "I tell @A to read me the tally, and say."}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Lettice Orme", "by": "ask", "why": "op_person"}
  · {"decision": "placed_in_scene", "name": "Lettice Orme", "unknown_place": "Saltmarrow [[L1]]", "place": "L1"}
  · {"decision": "pencilled_in", "names": ["Lettice Orme"]}
  prose end: alvage haul, and twelve gold is more than most make in a week. "I'll pay what I can from it. Lead me to the site." "Come then," they say, "but it's at the coast road end, a quarter hour's walk. The reeve's man there is named Elric. Elric will see you have it."

## T3 (11.69s, 0 calls)
  > I ask @A what exactly I owe the guild, and I won't go anywhere until I hear a number.
  at Saltmarrow | gold 12 | hp 20 | energy 16 | +5 min
  die item:tally item_count small 1=1
  die check:persuasion check success 1d20=6
  · {"decision": "absent_not_an_opponent", "names": ["Lettice Orme"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Person 1", "why": "A message runner is usually low-status and unlikely to question or defy the guild, especia
  · {"decision": "speech_said_before_dropped", "lines": ["\"I have a tally for you,\" they say, and then pause, waiting for you to ask what it's for."]}
  · {"decision": "name_is_a_person", "name": "Marion Glover", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "wide", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "tally", "quantity": 1}
  · {"decision": "refused", "item": {"name": "tally", "tokens": ["tally"], "outcome": null, "taken_unasked": false}}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: You stand in the shade of a wide awning on the salt-crusted street of Saltmarrow [[L1]]. Beside you, a messenger with wind-reddened eyes waits, holding a weathered leather tally.

## T4 (10.84s, 0 calls)
  > I give up on the number for now and say I'll take the salvage job; I ask the messenger what it pays me.
  at Saltmarrow | gold 12 | hp 20 | energy 16 | +5 min
  inv + ['salvage job x1']
  die item:salvage job item_count small 1=1
  die check:persuasion check failure 1d20=4
  · {"decision": "absent_not_an_opponent", "names": ["Lettice Orme"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most would still consider the salvage job, despite the lower pay"}
  · {"decision": "noun_is_no_figure", "kind": "thrill", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "sketch_identity_asked", "name": "Lettice Orme", "asked": ["A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Lettice Orme", "evidence": "prose_code"}
  prose end: , of course. It's not a big job, but it'll keep you fed and in gear for a while." She eyes your patched tunic and wool trousers. "Depends on what you find, I suppose." You can't help but feel a thrill at the idea of a job, even a small one. It's been too long.

## T5 (14.3s, 0 calls)
  > I tell @B I'll go to the site, and ask where I'm meant to find the reeve's man Elric.
  at Saltmarrow -> Coast Road | gold 12 | hp 20 | energy 16 | +5 min
  new rows: {"npcs": {"rows": ["#3 Dunstan"], "writes": [1, 7, 9, 14, 17, 25, 44]}, "locations": {"rows": ["#2 Coast Road"], "writes": [18, 19, 22]}}
  die check:persuasion check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Lettice Orme", "why": "A few messengers might be reluctant to approach a site, but most would accept the task
  · {"decision": "name_is_a_person", "name": "Melisent Pennick", "by": "ask", "why": "op_person"}
  · {"decision": "name_fits_the_sex_shown", "given": "Melisent Pennick", "drawn": "Dunstan", "shown": "male"}
  · {"decision": "new_place_in_town", "place": "Coast Road", "town": "Saltmarrow"}
  · {"decision": "filed_at_player_place", "code": "C", "name": "Dunstan", "was": 1, "now": 2, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Dunstan"]}
  prose end: b at all." She steps back, leaving you to consider what she's said. The coast road is only a few miles distant. And the reeve's man Elric sounds like a man who will expect perfection. But a job is a job, and you'll take what you can get to keep moving forward.

## T6 (7.94s, 0 calls)
  > I walk out along the coast road toward the old lighthouse.
  at Coast Road -> The Old Lighthouse | gold 12 | hp 20 | energy 16 | +6 min
  new rows: {"locations": {"rows": ["#3 The Old Lighthouse"], "writes": [6, 7, 11]}}
  · {"decision": "civic_building_requested", "place": "The Old Lighthouse", "made": true}
  · {"decision": "left_for_named_place", "left": "Coast Road", "destination": "The Old Lighthouse"}
  prose end: n the hillside toward the road. You pass the shepherd and her sheep without a word. They move off the road, keeping to the grassy verge as you continue onward. The lighthouse seems to grow no closer as the road winds along. You'll be walking for some time yet.

## T7 (11.15s, 0 calls)
  > I keep walking until I reach the lighthouse, then look around for the reeve's man Elric.
  at The Old Lighthouse | gold 12 | hp 20 | energy 16 | +6 min
  new rows: {"npcs": {"rows": ["#4 Elric"], "writes": [10, 13, 34, 35]}, "gm_events": {"rows": ["#1 Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present."], "writes": [27]}}
  die check:perception check failure 1d20=5
  · {"decision": "name_is_a_person", "name": "Elric", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Elric"]}
  · {"decision": "sketch_identity_asked", "name": "Elric", "asked": ["B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Elric", "evidence": "conversation"}
  prose end:  sea stretching out below. The door is shut and bolted. You rap on the door with your knuckles. After a moment, the bolt slides back and the door opens. A middle-aged woman with short grey hair looks out at you. She wears a grey reeve's cloak. "Yes?" she asks.

## T8 (20.63s, 0 calls)
  > I tell her I'm Isk Tarrow, the salvage guild's runner, and ask if she is Elric, the reeve's man.
  at The Old Lighthouse | gold 12 | hp 20 | energy 16 | +5 min
  die check:persuasion check failure 1d20=5
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "Most salvagers are honest and open about their identities and business."}
  · {"decision": "stays_as_shown", "place": "The Old Lighthouse", "status": "not_travel"}
  · {"decision": "new_place_not_shown", "name": "The deputy's office inside Saltmarrow"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: Elric [[D]] looks up from the papers she's sorting through, a flicker of surprise crossing her face. "Isk Tarrow, the guild's runner," he says, setting down his pen. "I didn't expect to find you in my office this early."

## T9 (22.47s, 0 calls)
  > I tell @D I came about the salvage job and ask what the pay is and what I'm to bring out of the drowned streets.
  at The Old Lighthouse | gold 12 | hp 20 | energy 16 | +5 min
  die check:persuasion check failure 1d20=3
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "Most salvagers would be interested in the pay and job details, as it's a common way to make a
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  prose end: er tone measured. "A third for the guild, a third for the reeve, and a third for you. But the work is dangerous. The streets are still restless, and the tide won't wait for you." He pauses, studying you. "What makes you think you're the right person for this?"

## T10 (13.37s, 0 calls)
  > I say I know the drowned lower district better than anyone alive, and I accept the third. I ask when the tide goes out.
  at The Old Lighthouse | gold 12 | hp 20 | energy 16 | +5 min
  die check:persuasion check success 1d20=9
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "A few in the crowd might question the claim but generally trust the deputy's judgment."}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "sketch_faded", "name": "Dunstan", "made": 6, "unmentioned_turns": 5}
  prose end: e depths at midnight, seeking vengeance. Beware." "South, down the Coast Road," Elric [[D]] says, pointing with one weathered hand. "Stay on the path. The reeve's patrols will not go beyond the lighthouse at night. You're on your own once you cross the river."

## T11 (15.42s, 0 calls)
  > I use Tidecount to feel when the flats will flood.
  at The Old Lighthouse | gold 12 | hp 20 | energy 14 | +6 min
  new rows: {"quests": {"rows": ["#1 Salvage Flats After Tide"], "writes": [38, 39, 40]}, "quest_steps": {"rows": ["#1 find exposed flats, salvage what's there"], "writes": [41]}}
  die skill:Tidecount skill_gain small 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "walk_inside_another_intent", "primary": "inventory", "destination": "(new place)"}
  · {"decision": "stays_as_shown", "place": "The Old Lighthouse", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "checked_offer_kept", "title": "Salvage Flats After Tide", "keyword_verdict": "no_offer_in_exchange"}
  prose end: sed flats at ebb tide. Elric [[D]] watches you, then crosses the room. "You've the tidecount," she says. "Have you seen the flats exposed? There's work to be found there, but the risk too. The salvage guild claims rights and dues. Stay safe, and good hunting."

## T12 (10.66s, 0 calls)
  > I thank Elric, tell her I'm heading back to Saltmarrow to the flats, and set off down the road to #L1.
  at The Old Lighthouse -> Saltmarrow | gold 12 | hp 20 | energy 14 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "inn", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "corner", "by": "ask", "first": false, "check": null}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "Saltmarrow"}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "outside Saltmarrow, on the road or in the wilds", "destination": "Saltmarrow"}
  prose end: ing your way to the flats district. The tenements and taverns grow more run-down the further from the harbor you get. This is the seedier side of Saltmarrow [[L1]] - perfect for your needs. You find a quiet corner and settle in to watch the comings and goings.

## T13 (13.27s, 0 calls)
  > I head down to the drowned lower district and start picking through the mud and rubble for anything worth salvaging.
  at Saltmarrow -> The Drowned Lower District | gold 12 | hp 20 | energy 14 | +6 min
  inv + ['BAND: small x1', 'brass medallion x1']
  new rows: {"locations": {"rows": ["#4 The Drowned Lower District"], "writes": [6, 7, 16, 21, 23]}}
  die item:brass medallion item_count small 1=1
  die item:BAND: small item_count small 1=1
  die skill:general skill_gain small 1=1
  · {"decision": "name_is_a_person", "name": "Bryony Lambard", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "medallion", "by": "ask", "first": false, "check": null}
  · {"decision": "model_move_dropped", "destination": "Saltmarrow [[L1]]", "why": "not_a_place"}
  · {"decision": "narration_code_skipped", "code": "L1", "why": "not_in_the_arrival_sentence"}
  · {"decision": "outdoor_area_requested", "place": "The Drowned Lower District", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Drowned Lower District"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_requested", "answer": "still in Saltmarrow", "destination": "The Drowned Lower District"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "brass medallion", "quantity": 1}
  · {"decision": "take_of_unowned_read_as_gain", "item": "BAND: small", "quantity": 1}
  prose end:  is still a rich patchwork of ancient refuse. The sea's dead lie buried here, and so do the memories of what was. You find a small brass medallion with strange runes on it. It looks like something from a very old faith. There are worse ways to spend a morning.

## T14 (15.12s, 0 calls)
  > I climb back up to #L1 and look for a trader in the market who'll buy a brass medallion.
  at The Drowned Lower District -> Saltmarrow | gold 12 | hp 20 | energy 12 | +10 min
  inv + ['brass x1']
  coins in prose: ['2 silver']
  die player.gold_delta 1d4=-4 (turn_bands)
  die item:brass item_count small 1=1
  die check:perception check success 1d20=13
  · {"decision": "place_bound_by_reference", "code": "L1", "place": "Saltmarrow", "words": "Saltmarrow"}
  · {"decision": "name_is_a_person", "name": "Tamsin", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "vendor", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Drowned Lower District", "confirm": "Yes, you are"}
  · {"decision": "loss_not_shown", "gold_delta": -4, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  prose end: uty says with a nod. "What have you got there?" You show them the medallion. "Looking to buy this. Might be worth something." They take the medallion and turn it over in their gloved hand. "I'll give you 2 silver for it, friend. That's a fair price for scrap."

## T15 (11.56s, 0 calls)
  > I say two silver is too low for old runed brass, and I ask for five silver or I keep it.
  at Saltmarrow | gold 12 | hp 20 | energy 12 | +5 min
  new rows: {"npcs": {"rows": ["#5 Stephen"], "writes": [6, 11, 14, 16, 36]}, "gm_events": {"rows": ["#2 Off-screen movement continues around Saltmarrow."], "writes": [29]}}
  coins in prose: ['Two silver', 'Five silver']
  die check:persuasion check success 1d20=13
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most would accept the price, as the runed brass is old and valuable."}
  · {"decision": "name_is_a_person", "name": "Mabel Joliffe", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "runner", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "unresolved"}
  · {"decision": "name_fits_the_sex_shown", "given": "Mabel Joliffe", "drawn": "Stephen", "shown": "male"}
  · {"decision": "placed_in_scene", "name": "Stephen", "unknown_place": "with wares spread out", "place": "L1"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Stephen"]}
  prose end: se. She doesn't glance your way. You come across a trader, sitting on a low wall with his wares spread out before him. He looks up and studies you for a moment. "Two silver for this old runed piece of scrap? You're dreaming. Five silver and it could be yours."

## T16 (12.14s, 0 calls)
  > I tell the trader I'm selling, not buying, and I'll take four silver for the medallion, no less.
  at Saltmarrow | gold 12 | hp 20 | energy 12 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "glint", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "sketch_identity_asked", "name": "Stephen", "asked": ["D", "B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Stephen", "evidence": "prose_code"}
  prose end: ppers browse the limited selection of goods, their voices mingling with the distant sounds of waves crashing against the shore. The sun is just beginning to rise, casting a soft pink glow over the scene as the first rays of light peek over the distant horizon.

## T17 (9.65s, 0 calls)
  > I tell @E plainly: the medallion, four silver, and I won't take less.
  at Saltmarrow -> Saltmarrow Store | gold 12 | hp 20 | energy 12 | +6 min
  new rows: {"locations": {"rows": ["#5 Saltmarrow Store"], "writes": [6, 7, 14]}}
  die item:medallion item_count small 1=1
  die item:silver item_count moderate 2=2
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_shown", "answer": "still in Saltmarrow", "destination": "Saltmarrow Store"}
  · {"decision": "gain_without_coin_dropped", "stated": 4, "why": "the prose shows no coin reaching the player"}
  · {"decision": "owned_item_not_new", "item": "medallion", "owned": "brass medallion"}
  · {"decision": "refused", "item": {"name": "silver", "tokens": ["silver"], "outcome": "unshown_loss"}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "payout_refused", "quest": "Salvage Flats After Tides", "reasons": ["evidence_not_in_text", "illegal_transition:offered->complete"], "quote": "", "passive": false}
  prose end: h. Inside, the store is dimly lit by sunlight filtering in through grimy windows. Shelves line the walls, laden with an assortment of goods - dry goods, sundries, and the occasional trinket. Stephen [[E]], a trader with grizzled features, eyes you up and down.

## T18 (10.13s, 0 calls)
  > I set the brass medallion on the counter in front of @E and wait for his offer.
  at Saltmarrow Store | gold 12 | hp 20 | energy 13 | +15 min
  die skill:perception skill_gain small 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "speech_said_before_dropped", "lines": ["\"Aye, what can I do for you, friend?\" he asks, his tone neutral enough, but with a hint of a challenge."]}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  · {"decision": "figure_is_known_person", "hint": "a weathered man"}
  prose end: e what he'll make of it. It's a strange piece, with intricate engravings on both sides. The trader picks it up, turning it over in his hands. He furrows his brow, studying it for a moment. "Where'd you get this?" he asks, his gaze still fixed on the medallion.

## T19 (16.95s, 0 calls)
  > I tell @E I dug it out of the mud in the drowned lower district this morning, and I ask what he'll pay for it.
  at Saltmarrow Store | gold 12 -> 11 | hp 20 | energy 13 | +5 min
  inv + ['leather pouch of gold x1']
  coins in prose: ['1 gold']
  die item:copper coin item_count small 1=1
  die item:leather pouch of gold item_count trivial 1=1
  die skill:persuasion skill_gain small 1=1
  die check:persuasion check success 1d20=20
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Stephen", "why": "Some traders might be interested in rare artifacts, but not all."}
  · {"decision": "speech_said_before_dropped", "lines": ["\"Aye, what can I do for you, friend?\" he says, eyeing the dull bronze medallion you're holding out."]}
  · {"decision": "name_is_a_person", "name": "Ralf Nettles", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside Saltmarrow Store", "confirm": "Yes, you are"}
  · {"decision": "settled", "detail": {"source": "stated", "gold_delta": -1, "offer": null, "model": -1}}
  prose end: a nod of thanks. The trader watches you go, the medallion now back in his hands. "Take care out there," he calls after you as you step out into the salt-worn streets of Saltmarrow [[L1]]. The light rain continues to fall, patterning the mud of the old cobbles.

## T20 (19.38s, 0 calls)
  > I count what is in the pouch and tell @E that a copper is an insult, then ask him for a fair price in silver.
  at Saltmarrow Store | gold 11 | hp 20 | energy 13 | +5 min
  coins in prose: ['two silver']
  die check:appraise check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  prose end: t you over his glasses as you show him the brass medallion you found in the ruins. "A fine piece, that," he says. "But a single coin won't pay for it. I'll give you two silver pieces for it, and that's fair." You pause and then ask, "Is that your final offer?"

## T21 (16.72s, 0 calls)
  > I agree to two silver, hand @E the brass medallion, and ask him to count the coins into my hand.
  at Saltmarrow Store | gold 11 | hp 20 | energy 13 | +5 min
  coins in prose: ['Two silvers', 'Two silvers']
  die check:persuasion check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Stephen", "why": "Some traders might hesitate to hand over a medallion without more proof of its value, but m
  · {"decision": "name_is_a_person", "name": "Delphine", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside Saltmarrow Store", "confirm": "Yes, you are"}
  · {"decision": "gain_without_coin_dropped", "stated": 2, "why": "the prose shows no coin reaching the player"}
  · {"decision": "refused", "item": {"name": "brass medallion", "tokens": ["brass", "medallion"], "outcome": null, "taken_unasked": false}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  prose end:  to you." He watches you for a moment, waiting to see what you will do next. The shop door is behind you, the street outside filled with the sounds of salt-marsh life, the calls of traders and the creak of carts. The money in your hand feels like a good start.

## T22 (12.64s, 0 calls)
  > I ask @E about the job he mentioned: who wants what, and what it pays.
  at Saltmarrow Store | gold 11 | hp 20 | energy 14 | +5 min
  new rows: {"quest_steps": {"rows": ["#2 Who wants what, and what it pays?"], "writes": [32, 33]}}
  die check:persuasion check success 1d20=14
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Stephen", "why": "Stephen is generally open to discussing business opportunities with others."}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  prose end: to a shelf with a knowing smile. "And then there's the matter of what you find out there, and who you find it from. But that's between us, yes?" It's more than you'd hoped for, but the risks are clear. Still, the brass tide-reckoner is a prize worth chasing...

## T23 (13.23s, 0 calls)
  > I close my hand over my mother's tide-reckoner and tell @E it is not for sale, not at any price.
  at Saltmarrow Store | gold 11 | hp 20 | energy 14 | +6 min
  new rows: {"gm_events": {"rows": ["#3 Rumors thicken away from the player; loyalties may shift before the next meeting."], "writes": [23]}}
  die check:appraise check failure 1d20=2
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "Salvage Flats After Tide", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  prose end: ou no time, not a second of the right hours. Not for all the brass in the flats." Stephen [[E]]'s weathered face hardens. "You know I'll have it. I've a client waiting. And I can be generous. How about a silver for the brass, and another for the right to ask?"

## T24 (12.79s, 0 calls)
  > I leave the store without selling and head to #L4, the drowned lower district, to look for more salvage before the tide turns.
  at Saltmarrow Store -> The Drowned Lower District | gold 11 | hp 20 | energy 14 | +6 min
  new rows: {"quest_steps": {"rows": ["#3 The rain soaks into your cloak as you start searching through the debris and wreckage for anything valuable that the\u2026"], "writes": [32, 33]}}
  die check:perception check success 1d20=21
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "model_move_dropped", "destination": "The Drowned Lower District [[L4]]", "why": "not_a_place"}
  prose end: . There is no one else around in the storm, just the sound of the rain and the waves lapping against the seawall. The rain soaks into your cloak as you start searching through the debris and wreckage for anything valuable that the tide hasn't yet carried away.

## T25 (11.53s, 0 calls)
  > I use Tidecount to feel when the flats will flood, then pick through the debris for anything worth keeping.
  at The Drowned Lower District | gold 11 | hp 20 | energy 13 | +6 min
  inv + ['gauge x1']
  die item:gauge item_count small 1=1
  · {"decision": "name_is_a_person", "name": "Jocelin Harrow", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "inventory", "destination": "(new place)"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Drowned Lower District", "confirm": "Yes"}
  prose end: s return is still some hours away. You continue picking through the debris, sifting through the remains of what was once a bustling harbour town. There's not much here that's valuable, but every little bit helps. The salvage guild will be expecting their dues.

## T26 (15.17s, 0 calls)
  > I tuck the brass gauge away and climb back up to #L1 to find the guild tallyman and settle my debt.
  at The Drowned Lower District -> Saltmarrow | gold 11 | hp 20 | energy 11 | +10 min
  new rows: {"npcs": {"rows": ["#6 Eadric"], "writes": [13, 33, 39]}}
  die check:athletics check success 1d20=11
  · {"decision": "place_bound_by_reference", "code": "L1", "place": "Saltmarrow", "words": "Saltmarrow"}
  · {"decision": "name_is_a_person", "name": "Eadric", "by": "ask", "why": "prose"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Drowned Lower District", "confirm": "Yes, you are"}
  · {"decision": "introduced_in_prose", "name": "Eadric", "role": "guild tallyman"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "pencilled_in", "names": ["Eadric"]}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Eadric", "pronouns": "he"}]}
  prose end: ]] takes it, weighing it in his hands. A smile spreads across his face as he nods. "Excellent. Your debt is cleared. The guild has use for capable hands like yours. If you're interested, there's always work to be found." But you've settled what you came to do.

## T27 (14.5s, 0 calls)
  > I never handed you anything, @F. Tell me the number I owe, in coin, and @A can witness it.
  at Saltmarrow | gold 11 | hp 20 | energy 11 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "at The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "role_kept", "name": "Lettice Orme", "kept": "message runner", "given": "local"}
  · {"decision": "sketch_identity_asked", "name": "Eadric", "asked": ["E", "D", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Eadric", "evidence": "prose_code"}
  prose end: u know where to come. Now if you'll excuse me..." He turns back to his ledgers, leaving you to walk up the road alone. The message runner, Lettice Orme [[B]], catches up to you at the Old Lighthouse [[L3]]. "A word with you, traveler?" she asks, her voice low.

## T28 (12.43s, 0 calls)
  > I wave her off and say I am no traveler, I am Isk Tarrow, and I ask @B what she wants with me.
  at Saltmarrow | gold 11 | hp 20 | energy 11 | +5 min
  new rows: {"quest_steps": {"rows": ["#4 Morning light spills through the open door of the Saltmarrow Store, casting long shadows on the salvagers haggling over\u2026"], "writes": [40, 41]}}
  die check:persuasion check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Lettice Orme", "why": "A few others might claim to be someone else, but most would not lie to a message runne
  · {"decision": "model_move_dropped", "destination": "[[L1]]", "why": "not_a_place"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  prose end:  no traveler, but Isk Tarrow. Then you ask her what she wants with you. "News has reached the Guild, Isk," she explains. "There are rumors of exposed salvage on the Flats, and the Guild seeks to claim it. But you have a claim on it as the liege of Saltmarrow."

## T29 (25.52s, 0 calls)
  > I ask @B about the exposed salvage on the Flats, where it is and what the Guild will pay me to bring it in.
  at Saltmarrow | gold 11 | hp 20 | energy 11 | +5 min
  new rows: {"quests": {"rows": ["#2 Deliver Exposed Salvage"], "writes": [43, 44, 45, 50]}, "quest_steps": {"rows": ["#5 Bring exposed salvaged goods to the Guild", "#6 You decide to ask about the Guild's offer for the exposed goods."], "writes": [46, 48, 49]}}
  die check:persuasion check success 1d20=19
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Lettice Orme", "why": "Lettice is paid to gather information and would have little reason to refuse this requ
  · {"decision": "speech_said_before_dropped", "lines": ["\"Liege Isk, I bring a message from the Guild. Will you join us for a chat?\"", "\"News has reached the Guild, Isk. There are rumors of exposed salvaged goods on the 
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  prose end: efore and can do it again. You decide to ask about the Guild's offer for the exposed goods. "It's not just a matter of what the Guild offers, but what you can bring them. The Guild is interested in rare items, things that can fetch a high price in Saltmarrow."

## T30 (15.87s, 0 calls)
  > @F, stop circling. I owe the guild a winter of credit. Name the number in coin and I will count it out of my eleven gold.
  at Saltmarrow | gold 11 | hp 20 | energy 11 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  prose end: alks off in the opposite direction, disappearing into the mist. You are left alone in the street, the mist swirling around your boots. The town of Saltmarrow [[L1]] is quiet but for the occasional sound of a door closing or a distant shout carried on the wind.

## T31 (7.87s, 0 calls)
  > I check my pouch and tell nobody in particular that I paid eleven gold, so why do I still count eleven? Then I head up to #L3 to report to @D Elric.
  at Saltmarrow -> The Old Lighthouse | gold 11 | hp 20 | energy 11 | +6 min
  new rows: {"gm_events": {"rows": ["#4 Off-screen movement continues around The Old Lighthouse."], "writes": [25]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "The Old Lighthouse", "words": "The Old Lighthouse"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end: re. You're nearly there. "Oi!" a shout cuts through the wind. You turn to see a figure running towards you. It's Elric [[D]], the guild tallyman from the lighthouse, his cloak billowing behind him. "Isk," he calls as he catches up, "I've been looking for you."

## T32 (11.24s, 0 calls)
  > I tell @D I salvaged the flats like she asked and ask for my third of the pay.
  at The Old Lighthouse | gold 11 | hp 20 | energy 11 | +5 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "coin_grant_dropped", "why": "the turn already moves gold by its GOLD op or a payment", "grants": ["coin"]}
  · {"decision": "gain_without_coin_dropped", "stated": 10, "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  prose end: Elric [[D]] looks up from the table where she's been poring over maps and ledgers, a surprised and pleased expression on her face. "Isk Tarrow," she says, standing up straight. "I've been meaning to have a word with you."

## T33 (8.58s, 0 calls)
  > I wait for her word, then say plainly: the flats are salvaged, so what is my third worth in coin, @D?
  at The Old Lighthouse | gold 11 | hp 20 | energy 12 | +15 min
  new rows: {"quest_steps": {"rows": ["#7 There's still work to be done, but for now, the coin in your pouch is enough to sate your hunger and ease your\u2026"], "writes": [30, 31]}}
  coins in prose: ['one silver']
  die check:appraise check failure 1d20=7
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end: oin, Deputy Reeve?" Elric [[D]] looks up at you, her gaze calculating. "Your third is worth one silver crown, flat-runner." There's still work to be done, but for now, the coin in your pouch is enough to sate your hunger and ease your weariness from the flats.

## T34 (19.62s, 0 calls)
  > One silver crown. I take it, @D, and ask her to put it in my hand so I can count it, then tell her what I found out there.
  at The Old Lighthouse | gold 11 | hp 20 | energy 12 | +5 min
  new rows: {"quest_steps": {"rows": ["#8 Found one good chest, some scrap metal, and a brass tide-reckoner."], "writes": [36, 37]}}
  die player.gold_delta 2d6+3=-9 (turn_bands)
  die check:persuasion check success 1d20=15
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "A silver crown is a significant sum, but not outrageous for a deputy to request. Most deputie
  · {"decision": "quote_said_by_a_person", "quote": "you've the tidecount."}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "payment_unpriced_banded", "band": "-small"}
  · {"decision": "loss_not_shown", "gold_delta": -9, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "settled", "detail": {"source": "payment_unpriced_band", "band": "-small", "offer": null}}
  prose end: the silver crown from her fingers. You count out the flat silver pieces. "Found one good chest, some scrap metal, and a brass tide-reckoner. All the salvage is out there." Elric [[D]] gives a tight smile. "You've done well, flat-runner. The tide's turned. Go."

## T35 (24.31s, 0 calls)
  > I ask @D what ails the dead at midnight, and whether the Guild will pay more if I bring something back from the flats tonight.
  at The Old Lighthouse | gold 11 | hp 20 | energy 12 | +5 min
  new rows: {"quest_steps": {"rows": ["#9 The tide brings them in, but it also takes them away."], "writes": [39, 40]}}
  die check:persuasion check success 1d20=7
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "cordial", "person": "Elric", "why": "Elric is curious and may offer a reward, but the reeve's deputy can't just ignore a direct qu
  · {"decision": "stays_as_shown", "place": "The Old Lighthouse", "status": "not_travel"}
  prose end: t also takes them away. It's the way of the sea." "As for the Guild," he continues, "they pay what they pay. If you bring back salvage, you'll be paid for it. But if you're looking for more..." He shakes his head. "There's no extra. The Guild's terms are set."

## T36 (14.88s, 0 calls)
  > !wait 360 sleep
  at The Old Lighthouse | gold 11 | hp 20 | energy 16 | +360 min
  · {"decision": "pronoun_pin_flipped_to_prose", "name": "Elric", "pronouns": "he", "evidence": {"he": 2, "she": 0}}
  prose end: lls. The brass tide-reckoner clicks and clacks on the table, keeping track of the hours and tides. Elric [[D]] watches the flat-runner, his eyes narrowed. "Have you found what you came for?" Elric [[D]] asks, his voice low. "Or do you still hunt for the dead?"

## T37 (14.35s, 0 calls)
  > I tell @D I am going out onto the flats tonight to wait for the dead, and ask what I should watch for.
  at The Old Lighthouse -> Saltmarrow | gold 11 | hp 20 | energy 16 | +15 min
  new rows: {"quest_steps": {"rows": ["#10 He looks at you, his eyes glinting in the candlelight."], "writes": [44, 45]}}
  die check:persuasion check success 1d20=17
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "watchful, world-weary", "person": "Elric", "why": "Elric is desperate for help with the dead problem, so most of the deputies woul
  · {"decision": "speech_said_before_dropped", "lines": ["\"You're asking about the dead?\" he says."]}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes"}
  prose end:  eyes glinting in the candlelight. "The exposed ones wash up on the saltflats. You'll know them when you see them. They're usually... not whole. Watch out for the scavengers. They'll rob you blind if you let them. You'll need to be quick and clever out there."

## T38 (13.97s, 0 calls)
  > I head down to #L4, the drowned lower district, and look for where the dead come ashore.
  at Saltmarrow -> The Drowned Lower District | gold 11 | hp 20 | energy 16 | +6 min
  new rows: {"npcs": {"rows": ["#7 Giselle"], "writes": [10, 13, 17, 20, 22, 38, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82]}}
  die check:perception check success 1d20=17
  · {"decision": "name_is_a_person", "name": "One", "by": "ask", "why": "prose"}
  · {"decision": "name_is_a_person", "name": "Giselle", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "lamp", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "still in Saltmarrow", "destination": "The Drowned Lower District"}
  · {"decision": "introduced_in_prose", "name": "One", "role": ""}
  · {"decision": "figure_referred_back_none_here", "kind": "woman"}
  · {"decision": "filed_at_player_place", "code": "G", "name": "Giselle", "was": 1, "now": 4, "why": "filed_here"}
  · {"decision": "pencilled_in", "names": ["Giselle", "Philippa"]}
  · {"decision": "merged_person", "merged": "Philippa, passerby, Someone at the edge of the scene.", "into": "Giselle, message runner"}
  · {"decision": "sketch_twin_collapsed", "name": "Philippa", "kept": "Giselle", "why": "beyond_figures_shown"}
  prose end: since. You're looking for any exposed flats where the storm might have left some salvage. The woman in the hood falls into step beside you. "The flats are just past the ruined church," she says quietly. "I've been watching the tides. You might find something."

## T39 (16.53s, 0 calls)
  > I walk with the hooded woman toward the ruined church and then settle down on a broken wall to wait for midnight. !wait 330 wait
  at The Drowned Lower District -> The Ruined Church | gold 11 | hp 20 | energy 16 | +-1090 min
  new rows: {"locations": {"rows": ["#6 The Ruined Church"], "writes": [12, 13, 20]}, "gm_events": {"rows": ["#5 Off-screen movement continues around The Ruined Church."], "writes": [33]}}
  die skill:general skill_gain small 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "civic_building_requested", "place": "The Ruined Church", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Ruined Church"}
  · {"decision": "sketch_identity_asked", "name": "Giselle", "asked": ["A", "B", "F"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Giselle", "evidence": "ops"}
  prose end: f the churchyard, and Giselle [[G]] settles down beside you. The air is thick with the scent of salt and decay. You wait in silence for the clock to strike midnight. Giselle [[G]] is alert, constantly scanning the shadows. She seems to know these streets well.

## T40 (14.76s, 0 calls)
  > It is midnight. I keep still and listen for anything dragging itself out of the churchyard, and I whisper to @G to stay behind me.
  at The Ruined Church | gold 11 | hp 20 | energy 16 | +6 min
  new rows: {"npcs": {"rows": ["#9 Peregrine"], "writes": [9, 14, 32]}}
  · {"decision": "name_is_a_person", "name": "Peregrine", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "emerge", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "The Ruined Church", "status": "not_travel"}
  · {"decision": "placed_in_scene", "name": "Peregrine", "unknown_place": "L1 Saltmarrow", "place": "L6"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "payout_refused", "quest": "Title: Deliver Exposed Salvage, accept", "reasons": ["evidence_not_in_text", "illegal_transition:offered->step_done"], "quote": "", "passive": true}
  · {"decision": "pencilled_in", "names": ["Peregrine"]}
  prose end: nd you. As you stand tense, listening, you hear slow dragging steps from behind you. You turn to see a hooded figure emerge from the graveyard. It drags a broken oar and seems to be searching the graves. The figure is too far away to make out much more detail.

## T41 (11.77s, 0 calls)
  > I draw my knife and stab at the dragging figure in the graveyard.
  at The Ruined Church | gold 11 | hp 20 | energy 14 | +6 min
  new rows: {"events": {"rows": ["#1 The Stabbing"], "writes": [17]}}
  die check:melee check success 1d20=14
  · {"decision": "attack_found", "target": {"code": "H", "name": "Peregrine"}, "source": "trigger", "skill": ""}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Ruined Church", "confirm": "Yes."}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "sketch_identity_asked", "name": "Peregrine", "asked": ["F", "B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Peregrine", "evidence": "ops"}
  prose end: our fist hits Peregrine [[H]]. It lets out a gurgling moan and thrashes against its bonds, trying to get away from you. The figure is Peregrine [[H]], the orchard keeper from Saltmarrow [[L1]]. He glares at you with wide eyes, his face a mask of pain and fear.

## T42 (13.16s, 0 calls)
  > I stab at Peregrine again and shove him back from the grave, shouting at him to keep away from me.
  at The Ruined Church | gold 11 | hp 19 (-1) | energy 12 | +6 min
  die check:melee check failure 1d20=3
  · {"decision": "attack_found", "target": {"code": "H", "name": "Peregrine"}, "source": "trigger", "skill": ""}
  · {"decision": "combat_follows_attack_check", "code": "H", "check_outcome": "failure", "was": "hit", "now": "miss", "damage": 0}
  · {"decision": "name_is_a_person", "name": "Giles Kirkby", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "The Ruined Church", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "title: Salvage Flats After Tide, step_done", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  prose end: u, fear in his eyes. Peregrine [[H]] is still alive. Without training, the weapon/tool does as much harm to you as to the world. You are unskilled at wielding this — you end up taking your own hand into the mess. Unskilled with Melee: you injure your own hand.

## T43 (18.69s, 0 calls)
  > I stop and say: Peregrine, you are no risen dead. Why were you dragging an oar through the graves at midnight?
  at The Ruined Church | gold 11 | hp 19 | energy 12 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Leofric Hayward", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "The Ruined Church", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "Q1", "reasons": ["evidence_not_in_text"], "quote": "", "passive": true}
  prose end: emerges from the gloom, his face a mask of confusion and pain. He holds a blood-stained oar in one hand. "Who are you?" he demands. "What are you doing here?" "Isk Tarrow," you answer. "I'm no threat. Why were you dragging that through the graves at midnight?"

## T44 (19.45s, 0 calls)
  > I lower my hands and tell Peregrine I took him for one of the risen dead; I ask him what he is doing here and if he has seen anything crawl out of the flats.
  at The Ruined Church | gold 11 | hp 19 | energy 12 | +5 min
  die item:brass item_count small 1=1
  die skill:perception skill_gain trivial 1=1
  die check:persuasion check success 1d20=8
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Peregrine", "why": "The player's request is reasonable and fits the character's role and background."}
  · {"decision": "noun_is_no_figure", "kind": "living", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Ruined Church", "confirm": "Yes, you are"}
  · {"decision": "refused", "item": {"name": "brass", "tokens": ["brass"], "outcome": null, "taken_unasked": false}}
  · {"decision": "figure_is_listed_person", "hint": "The orchard keeper"}
  prose end:  says. "Most of them are just after what's left to take. Not many care about making a living from what the sea gives up." He offers to show you a spot along the flats where he's seen some exposed brass. "It's not much," he says. "But it's better than nothing."

## T45 (11.63s, 0 calls)
  > I follow Peregrine out of the church and onto the flats, keeping my knife out and my eyes on the mud for anything that moves.
  at The Ruined Church -> The Old Lighthouse | gold 11 | hp 19 | energy 12 | +6 min
  new rows: {"events": {"rows": ["#2 Salvage Hunt"], "writes": [12, 15]}}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "outside Saltmarrow, on the road or in the wilds", "destination": "The Old Lighthouse"}
  · {"decision": "role_kept", "name": "Peregrine", "kept": "orchard keeper", "given": "local"}
  prose end: worked. He pockets it and looks around. You crouch down beside him and see faint tracks in the mud leading out to the water's edge. Peregrine [[H]] looks at you, his eyes gleaming in the starlight. "The tide is turning," he says. "Come. There is more to find."

## T46 (17.48s, 0 calls)
  > I leave Peregrine and push out alone into the salt marsh, stepping softly, listening for whatever dragged itself out of the mud tonight.
  at The Old Lighthouse -> The Salt Marsh | gold 11 | hp 19 | energy 12 | +6 min
  new rows: {"locations": {"rows": ["#7 The Salt Marsh", "#8 Old Ruins"], "writes": [6, 7, 11, 12]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "walk_inside_another_intent", "primary": "investigation", "destination": "(new place)"}
  · {"decision": "outdoor_area_requested", "place": "The Salt Marsh", "made": true}
  · {"decision": "requested_place_before_minted", "destination": "The Salt Marsh"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  prose end: ace is unrecognizable. Peregrine [[H]] meets your gaze, his expression pained. "I found him out here, near the old ruins. I meant to bring him to the reeve, but... I'm not sure I can drag him that far." You look between Peregrine [[H]] and the body, uncertain.

## T47 (16.05s, 0 calls)
  > I kneel by the body and search it for what killed him, checking his hands and pockets and the wounds.
  at The Salt Marsh | gold 11 | hp 19 | energy 11 | +15 min
  new rows: {"gm_events": {"rows": ["#6 offscreen", "#7 A delayed consequence of recent public actions continues off-screen."], "writes": [11, 23]}}
  die check:perception check success 1d20=11
  · {"decision": "noun_is_a_figure", "kind": "form", "by": "ask", "first": true, "check": true}
  · {"decision": "figure_not_hostile", "kind": "form"}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  prose end: g a distance. You rise slowly to your feet, trying to show no fear. The animal bares its fangs in a snarl and snaps at the ground at your feet. It is guarding the body, and will not let you near it. The tide is almost in; soon there will be no dry ground left.

## T48 (17.72s, 0 calls)
  > I back off a step, then stab at the snarling creature with my knife to drive it off the body.
  at The Salt Marsh | gold 11 | hp 19 | energy 9 | +6 min
  die check:melee check success 1d20=19
  · {"decision": "name_is_a_person", "name": "Edmund", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "moment", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Salt Marsh", "confirm": "Yes, you are"}
  · {"decision": "refused", "item": {"name": "salvage job contract", "tokens": ["salvage", "contract"], "outcome": null, "taken_unasked": false}}
  prose end: from the darkness, his tunic patched and his boots worn. He stops a few paces from you and stares intently. "You've got the look of someone who's been out on the marshes," he says finally, his voice low. "Peregrine sent me to find you. Said you might be here."

## T49 (23.03s, 0 calls)
  > I keep my hand off the knife and ask the stranger who he is and what Peregrine wants with me.
  at The Salt Marsh | gold 11 | hp 19 | energy 9 | +5 min
  new rows: {"npcs": {"rows": ["#10 Bertram Forester"], "writes": [10, 13, 36]}}
  die check:persuasion check success 1d20=19
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most ordinary people in the same situation would also ask the stranger about their identity and motives b
  · {"decision": "role_was_a_note", "name": "Bertram Forester", "note": "works at The Salt"}
  · {"decision": "name_is_a_person", "name": "Bertram Forester", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  · {"decision": "figure_is_listed_person", "hint": "a rough-looking man"}
  · {"decision": "figure_referred_back_none_here", "kind": "stranger"}
  · {"decision": "pencilled_in", "names": ["Bertram Forester"]}
  prose end: e says. "Peregrine is my cousin, and he asked me to find you. He's at the Old Lighthouse, says you're the one to talk to about that salvage job you're on." With a nod, he turns and walks off into the darkness of the marsh, leaving you alone with your thoughts.

## T50 (15.24s, 0 calls)
  > I tell Bertram I will take the dead man to the reeve myself, and ask him to help me carry the body toward the Old Lighthouse.
  at The Salt Marsh -> The Old Lighthouse | gold 11 | hp 19 | energy 9 | +5 min
  die check:persuasion check failure 1d20=4
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Bertram Forester", "why": "Most mole catchers would help carry a body to the reeve, as it is the responsible 
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "The Old Lighthouse"}
  · {"decision": "model_move_replaced_by_player_destination", "model_destination": "Old Ruins", "player_destination": "The Old Lighthouse"}
  · {"decision": "where_ended_not_confirmed", "answer": "at The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "figure_is_listed_person", "hint": "the dead man"}
  · {"decision": "sketch_identity_asked", "name": "Bertram Forester", "asked": ["F", "B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Bertram Forester", "evidence": "ops"}
  prose end: is spade slung over his shoulder. You trudge through the night, the salt wind tugging at your clothes, the dead man's weight a leaden burden. The Old Lighthouse [[L3]] looms ahead, a skeletal tower on the cliff's edge, its lamp a dim red eye watching the dark.

## T51 (18.42s, 0 calls)
  > I set the dead man down by the lighthouse door and call out to @D that I have brought a body from the salt marsh for the reeve.
  at The Old Lighthouse | gold 11 | hp 19 | energy 9 | +6 min
  new rows: {"npcs": {"rows": ["#11 Warin"], "writes": [10, 13, 37]}}
  die player.gold_delta 2d6+3=-12 (turn_bands)
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "place_left_not_destination", "place": "The Salt Marsh"}
  · {"decision": "name_is_a_person", "name": "Jehane Harrow", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "moment", "by": "ask", "first": false, "check": null}
  · {"decision": "place_left_not_destination", "place": "The Salt Marsh"}
  · {"decision": "place_left_not_destination", "place": "The Salt Marsh"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes"}
  · {"decision": "name_fits_the_sex_shown", "given": "Jehane Harrow", "drawn": "Warin", "shown": "male"}
  · {"decision": "loss_not_shown", "gold_delta": -12, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "payout_refused", "quest": "Salvage Flats AfterTide", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["Warin"]}
  prose end: puty's eyes narrow, but he says nothing more before turning back to the interior of the lighthouse. You wait a moment, watching the flicker of light from within, before turning to leave the dead man at the lighthouse door and make your way back into the night.

## T52 (18.14s, 0 calls)
  > I stop Elric before he shuts the door and ask @D to pay me what the reeve owes for the salvage flats work, the fifteen gold the job promised.
  at The Old Lighthouse | gold 11 | hp 19 | energy 9 | +5 min
  coins in prose: ['fifteen gold', 'fifteen gold', 'fifteen gold']
  die check:persuasion check success 1d20=10
  · {"decision": "absent_not_an_opponent", "names": ["Peregrine", "Warin"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "cordial", "person": "Elric", "why": "Most people would be too intimidated or cautious to directly confront the reeve's deputy abou
  · {"decision": "name_is_a_person", "name": "Godfrey Pollard", "by": "ask", "why": "op_person"}
  · {"decision": "coin_grant_dropped", "why": "the turn already moves gold by its GOLD op or a payment", "grants": ["gold"]}
  · {"decision": "gain_without_coin_dropped", "stated": 15, "why": "the prose shows no coin reaching the player"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "corpse", "quantity": 1}
  · {"decision": "refused", "item": {"name": "corpse", "tokens": ["corpse"], "outcome": "loss", "taken_unasked": false}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  prose end: pse, then the closed doors. "Alright then. Give me a moment to fetch the coin." Elric [[D]] moves to a table and returns with a small leather purse. He tosses it to you. "There's your fifteen gold. Now, about that... corpse." "As promised. No trouble, deputy."

## T53 (17.72s, 0 calls)
  > I open the purse and count the coins out onto my palm, then tell @D the count and ask him to mark Q1 as paid.
  at The Old Lighthouse | gold 11 | hp 19 | energy 9 | +5 min
  new rows: {"events": {"rows": ["#3 Salvage Claim Settled"], "writes": [17]}}
  coins in prose: ['Fifteen gold']
  die item:15 gold item_count trivial 1=1
  die check:persuasion check success 1d20=13
  · {"decision": "absent_not_an_opponent", "names": ["Peregrine", "Warin"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "cordial", "person": "Elric", "why": "A few people in Elric's position would refuse, as they may not have the authority or resource
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "gain_without_coin_dropped", "stated": 15, "why": "the prose shows no coin reaching the player"}
  · {"decision": "refused", "item": {"name": "15 gold", "tokens": ["gold"], "outcome": "unshown_loss"}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "payout_refused", "quest": "Salvage Flats After Tide; accept", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  prose end: settled." You hand him the coins. "That's fair. I'll take it." Elric [[D]] nods and counts the coins. "Seems we both got what we wanted out of this. I'll mark it down." He jots something on a scrap of paper, then holds it out to you. "Here you go. Your proof."

## T54 (13.35s, 0 calls)
  > I leave the lighthouse and head to #L5 to buy something cheap from the store.
  at The Old Lighthouse -> Saltmarrow Store | gold 11 | hp 19 | energy 9 | +6 min
  new rows: {"npcs": {"rows": ["#12 = Marcella"], "writes": [9, 33]}}
  · {"decision": "place_bound_by_reference", "code": "L5", "place": "Saltmarrow Store", "words": "Saltmarrow Store"}
  · {"decision": "name_is_a_person", "name": "= Marcella", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_disagrees", "destination": "Saltmarrow Store", "answer": "in Saltmarrow, outside The Old Lighthouse"}
  · {"decision": "placed_in_scene", "name": "= Marcella", "unknown_place": "= [[L4]]", "place": "L5"}
  · {"decision": "payout_refused", "quest": "quest = 'Find Supplies'; accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["= Marcella"]}
  prose end: ll and lean, with a shawl wrapped around her head. She steps into your path. "Evening," she says. "Need a light coat? Some boots maybe? I've got things." You stop and look at her. She's not one of the storekeepers, but a peddler come out of the ruins to trade.

## T55 (8.09s, 0 calls)
  > I look over her wares and say I pay two copper for a tallow candle, if she has one.
  at Saltmarrow Store | gold 11 | hp 19 | energy 9 | +6 min
  new rows: {"gm_events": {"rows": ["#8 A delayed consequence of recent public actions continues off-screen."], "writes": [21]}}
  coins in prose: ['two silver', 'Two copper']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  · {"decision": "figure_is_one_here", "kind": "peddler", "names": ["= Marcella"]}
  · {"decision": "sketch_identity_asked", "name": "= Marcella", "asked": ["F", "B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "= Marcella", "evidence": "ops"}
  prose end:  a peddler standing near the door, a hooded cloak drawn tight. They glance at you and away, as if considering something. "Two copper for a tallow candle, you say?" the peddler repeats softly. "I've a few left, in my pack. If you want one, I'll take your word."

## T56 (16.77s, 0 calls)
  > I hand the peddler two copper and take the candle.
  at Saltmarrow Store | gold 11 | hp 19 | energy 9 | +6 min
  inv + ['candle x1']
  new rows: {"npcs": {"rows": ["#13 Avelina Ridley"], "writes": [9, 15, 17, 36, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56]}}
  coins in prose: ['Two copper', 'Two copper', 'One copper']
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Avelina Ridley", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "candle", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_one_here", "kind": "peddler", "names": ["= Marcella"]}
  · {"decision": "filed_at_player_place", "code": "M", "name": "Avelina Ridley", "was": 3, "now": 5, "why": "filed_here"}
  · {"decision": "payout_refused", "quest": "Q1", "reasons": ["evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["Avelina Ridley"]}
  · {"decision": "sketch_faded", "name": "Warin", "made": 52, "unmentioned_turns": 5}
  prose end: holding up a small wax candle. "One copper to light your way. The other buys you a little warmth at your hearth." You choose the peddler's candle and tuck it into your tunic. Stephen [[E]] watches, saying nothing. The peddler smiles and steps out into the fog.

## T57 (11.43s, 0 calls)
  > I ask @E whether he has seen who the dead man at the lighthouse door might be, and how much the brass medallion is worth to him.
  at Saltmarrow Store | gold 11 | hp 19 | energy 9 | +5 min
  die check:persuasion check success 1d20=10
  · {"decision": "absent_not_an_opponent", "names": ["Avelina Ridley"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "disappointed but persistent", "person": "Stephen", "why": "A trader might share information or make a business deal for the right 
  · {"decision": "place_not_gone_to", "code": "L3", "words": "the lighthouse", "reply": "No, the player"}
  · {"decision": "common_noun_names_known_place", "noun": "lighthouse", "place": "The Old Lighthouse"}
  · {"decision": "common_noun_names_known_place", "noun": "lighthouse", "place": "The Old Lighthouse"}
  · {"decision": "common_noun_names_known_place", "noun": "lighthouse", "place": "The Old Lighthouse"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  prose end: eneath a worn, salt-stained cap. "I've seen the body at the lighthouse, and I've seen the brass medallion," he says, his voice low and guarded. "But it's not mine to sell. The lighthouse is a holy place." You persist, hoping to glean more information from him.

## T58 (11.36s, 0 calls)
  > I use Tidecount to feel when the flats will flood.
  at Saltmarrow Store | gold 11 | hp 19 | energy 7 | +6 min
  new rows: {"npcs": {"rows": ["#14 Marcella"], "writes": [8, 12, 16, 36, 40]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Marcella", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "inventory", "destination": "(new place)"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "unresolved"}
  · {"decision": "figure_is_listed_person", "hint": "A peddler"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Marcella"]}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Marcella", "pronouns": "she"}]}
  prose end: w so much about the tides, traveler?" she asks, her voice a whisper. Stephen [[E]] steps out from behind the counter, his weathered face betraying a hint of concern. "The flats are treacherous, friend. Better to leave such matters to those who know them well."

## T59 (14.95s, 0 calls)
  > I buy nothing more and head to #L3 to see whether the dead man still lies at the lighthouse door.
  at Saltmarrow Store -> The Old Lighthouse | gold 11 | hp 19 | energy 7 | +6 min
  new rows: {"events": {"rows": ["#4 Event"], "writes": [10, 13]}, "gm_events": {"rows": ["#9 offscreen"], "writes": [14]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "place_bound_by_reference", "code": "L3", "place": "The Old Lighthouse", "words": "The Old Lighthouse"}
  · {"decision": "common_noun_names_known_place", "noun": "lighthouse", "place": "The Old Lighthouse"}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "in Saltmarrow, outside Saltmarrow Store", "destination": "The Old Lighthouse"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "dagger", "text": "You approach cautiously, your hand resting on the hilt of your dagger."}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  prose end: ing before the lighthouse doors, as if he has been here for a long time. The fog seems to swirl and sigh all around you, as if it is a living thing. You pause, uncertain, before pushing open the heavy lighthouse doors and stepping inside to get out of the fog.

## T60 (13.62s, 0 calls)
  > I turn back to the body in the doorway, kneel, and search its coat and boots for a name, a mark or a purse.
  at The Old Lighthouse | gold 11 | hp 19 | energy 6 | +15 min
  inv + ["reeve's crest medallion x1"]
  die item:reeve's crest medallion item_count small 1=1
  die skill:Investigation skill_gain trivial 1=1
  die check:perception check success 1d20=12
  · {"decision": "name_is_a_person", "name": "Silas Radley", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "purse", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "medallion", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes."}
  · {"decision": "take_of_unowned_read_as_gain", "item": "reeve's crest medallion", "quantity": 1}
  prose end: an see - just a tattered cloak and patched boots. But you find a small leather purse. You open it and find a silver medallion with the image of a reeve's crest stamped upon it. You don't recognize the name on the body, but the reeve's deputy Elric [[D]] might.

## T61 (17.47s, 0 calls)
  > I carry the crest medallion inside and show it to @D, asking him whose it was and whether he will pay me for bringing the body in.
  at The Old Lighthouse | gold 11 | hp 19 | energy 6 | +6 min
  die check:persuasion check success 1d20=20
  · {"decision": "absent_not_an_opponent", "names": ["Peregrine"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "A few people might be loyal enough to the reeve's deputy to follow this request, but many wou
  · {"decision": "stays_as_shown", "place": "The Old Lighthouse", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "sketch_faded", "name": "Avelina Ridley", "made": 57, "unmentioned_turns": 5}
  prose end: f the flats." You pocket the medallion and consider his offer. The flats are exposed for only a few hours after the tide recedes. If you can find valuable salvage, Elric [[D]] might pay you. But he makes it clear you're not to keep the best finds for yourself.

## T62 (15.96s, 0 calls)
  > I tell @D I will not leave the dead man lying in the fog, and ask him to lend me a spade so I can bury him on the cliff.
  at The Old Lighthouse | gold 11 | hp 19 | energy 6 | +5 min
  die item:spade item_count small 1=1
  die check:persuasion check partial 1d20=4
  · {"decision": "absent_not_an_opponent", "names": ["Peregrine"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "Most people would not refuse help from a fellow deputy, especially in a dangerous situation l
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "gain_without_coin_dropped", "stated": 15, "why": "the prose shows no coin reaching the player"}
  · {"decision": "refused", "item": {"name": "spade", "tokens": ["spade"], "outcome": null, "taken_unasked": false}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "figure_is_listed_person", "hint": "the dead man"}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  prose end: ]] frowns, considering. "You're asking a lot," he says at last. "The reeve's men will have a spade. If you bring it back to them, you'll get a small reward. Nothing else." He eyes you, gauging. "But if I help you, what's in it for me? Valuable finds, perhaps?"

## T63 (17.66s, 0 calls)
  > I promise @D I will bring the spade back by dawn and with it any good salvage I find, then I take the spade and drag the dead man toward the cliff to bury him.
  at The Old Lighthouse | gold 11 | hp 19 | energy 6 | +6 min
  new rows: {"npcs": {"rows": ["#15 Reinald Barrow"], "writes": [9, 12, 36, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56]}, "gm_events": {"rows": ["#10 A delayed consequence of recent public actions continues off-screen."], "writes": [26]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Reinald Barrow", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, you are"}
  · {"decision": "placed_in_scene", "name": "Reinald Barrow", "unknown_place": "The Drowned Lower District [[L4]]", "place": "L3"}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "pencilled_in", "names": ["Reinald Barrow"]}
  · {"decision": "sketch_faded", "name": "Marcella", "made": 59, "unmentioned_turns": 5}
  prose end: ry him." Elric [[D]] nods. "Very well," he says. "I'll keep watch here. You'd best be quick about it." He hands over the spade, a heavy thing of iron with a wooden handle. You take it, feeling its weight, and turn to the dark shape of the dead man on the sand.

## T64 (13.96s, 0 calls)
  > I drag the dead man up the cliff path and dig a grave with the spade, then lay him in it and fill it in.
  at The Old Lighthouse | gold 11 | hp 19 | energy 2 | +25 min
  new rows: {"events": {"rows": ["#5 Grave Dug"], "writes": [15]}}
  die skill:Athletics skill_gain trivial 1=1
  die check:athletics check success 1d20=17
  · {"decision": "absent_not_an_opponent", "names": ["Peregrine", "Reinald Barrow"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "grave", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes, the text"}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: ing and clods falling until the grave looks like it will stay. Elric [[D]] watches you work, the reeve's crest medallion on his cloak glinting in the starlight. "That's the third grave you've dug this tide," he says solemnly. "The sea gives and the sea takes."

## T65 (19.22s, 0 calls)
  > !wait 360 sleep
  at The Old Lighthouse | gold 11 | hp 20 (+1) | energy 15 | +360 min
  new rows: {"npcs": {"rows": ["#16 Clement"], "writes": [4]}, "quest_steps": {"rows": ["#11 You'd brought exposed salvaged goods here to the Guild, but the Guild's captain, Eadric, had yet to appear."], "writes": [33, 34]}}
  · {"decision": "speech_said_before_dropped", "lines": ["The Guild's rules are clear."]}
  prose end: d salvaged goods here to the Guild, but the Guild's captain, Eadric [[F]], had yet to appear. You waited, the brass arms of the tide-reckoner spinning slow as the tide. Minutes stretched on. The ticking filled the hall. Elric [[D]] shifted, his gaze lingering.

## T66 (20.06s, 0 calls)
  > The tide has gone out now. I head to #L4 and pick through the exposed flats for salvage to take to the guild.
  at The Old Lighthouse -> Saltmarrow Salvage Yard | gold 11 | hp 20 | energy 15 | +6 min
  new rows: {"locations": {"rows": ["#9 Saltmarrow Salvage Yard"], "writes": [9, 10, 19]}, "quest_steps": {"rows": ["#12 Elric calls down to you again as you finish,"], "writes": [45, 46]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "speech_said_before_dropped", "lines": ["Best not test their patience further."]}
  · {"decision": "place_bound_by_reference", "code": "L4", "place": "The Drowned Lower District", "words": "The Drowned Lower District"}
  · {"decision": "name_is_a_person", "name": "Ingram Bexley", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "glint", "by": "ask", "first": false, "check": null}
  · {"decision": "model_move_dropped", "destination": "Saltmarrow Store You head back up the shore to the Old Lighthouse with your haul.", "why": "not_a_place"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Old Lighthouse", "confirm": "Yes"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "iron nail", "quantity": 12}
  · {"decision": "refused", "item": {"name": "silver pendant", "tokens": ["silver", "pendant"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "belt buckle", "tokens": ["belt", "buckle"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "copper pendant", "tokens": ["copper", "pendant"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "iron nail", "tokens": ["iron", "nail"], "outcome": null, "taken_unasked": false}}
  prose end: me small haul scattered across the flats. You gather what you can and pack it all into a burlap sack. Elric [[D]] calls down to you again as you finish, "Third times you've dug graves this cycle already. You'll need more than a few coins to settle your debts."

## T67 (17.39s, 0 calls)
  > I carry the sack of salvage to #L1 and put it in front of @F, telling him it is exposed salvage for the guild and I want what the guild owes for it.
  at Saltmarrow Salvage Yard | gold 11 | hp 20 | energy 15 | +6 min
  new rows: {"quest_steps": {"rows": ["#13 Eadric looks over the sack, then back at you."], "writes": [33, 34]}}
  coins in prose: ['80 silver', '80 silver']
  · {"decision": "place_bound_by_reference", "code": "L1", "place": "Saltmarrow", "words": "Saltmarrow"}
  · {"decision": "name_is_a_person", "name": "Margery Thackeray", "by": "ask", "why": "op_person"}
  · {"decision": "coin_grant_dropped", "why": "the turn already moves gold by its GOLD op or a payment", "grants": ["silver"]}
  · {"decision": "offered_sum_not_received", "stated": 80}
  · {"decision": "settled", "detail": {"source": "offered_sum_not_received", "gold_delta": 0, "offer": null}}
  · {"decision": "sketch_faded", "name": "Reinald Barrow", "made": 64, "unmentioned_turns": 5}
  prose end: tch a fair price, yes. But the guild takes 20% for handling. You'll get 80 silver for it." He grins. "No promises on how much it'll fetch. Market's been slow. But I'll write you a claim for 80 silver when it sells. You'll get your coin when the tally is done."

## T68 (24.1s, 0 calls)
  > I say I will take the eighty silver now, in coin, not a claim, and ask @F to mark my salvage job as delivered.
  at Saltmarrow Salvage Yard | gold 11 | hp 20 | energy 16 | +5 min
  inv + ['eighty silver x1', 'salvage job claim x1']
  new rows: {"quest_steps": {"rows": ["#14 Ah, Isk, I see you've brought what we discussed to the guild."], "writes": [50, 51]}}
  die item:eighty silver item_count small 1=1
  die check:persuasion check success 1d20=18
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Eadric", "why": "The request is reasonable and within the scope of a guild tallyman's duties."}
  · {"decision": "noun_is_no_figure", "kind": "claim", "by": "ask", "first": false, "check": null}
  · {"decision": "take_of_unowned_read_as_gain", "item": "salvage job claim", "quantity": 1}
  prose end:  then. Just mark my job as done, will you?" "Of course," Eadric [[F]] says, dipping his quill once more. "It's marked. You've done good work here, Isk. The guild will be looking for more like you. Keep an eye out for more salvage to expose. We'll be in touch."

## T69 (11.94s, 0 calls)
  > I tell @F I am going to hunt whatever dragged itself out of the mud, and head to #L7, the salt marsh.
  at Saltmarrow Salvage Yard -> The Salt Marsh | gold 11 | hp 20 | energy 16 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Yolande Dunmorse", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "footprint", "by": "ask", "first": false, "check": null}
  · {"decision": "model_move_dropped", "destination": "The Salt Marsh [[L7]]", "why": "not_a_place"}
  prose end: er to follow the tracks. The reeds are thick and the footing treacherous, but the promise of a clue about what dragged itself out of the mud drives you forward. With a deep breath, you step into the salt marsh [[L7]] and begin to wade through the tall grasses.

## T70 (15.58s, 0 calls)
  > I crouch at the footprints and follow them through the reeds, knife in hand, looking for the creature.
  at The Salt Marsh | gold 11 | hp 20 | energy 16 | +6 min
  new rows: {"gm_events": {"rows": ["#11 Bertram Forester pursues private business that may matter later."], "writes": [27]}}
  die check:perception check success 1d20=20
  · {"decision": "noun_is_no_figure", "kind": "hand", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "tentative", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "unresolved"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "travel_unresolved", "note": "Followed them with no place named; the player stayed in The Salt Marsh."}
  prose end: nd begins to retreat back the way they came. With a sigh, you stand up and begin to follow the footprints once more, wondering if you'll catch up with this stranger and get some answers. The mist continues to swirl around you as you push deeper into the marsh.

## T71 (16.16s, 0 calls)
  > I sprint after the ragged figure through the shallows and shout for it to stop, my knife ready.
  at The Salt Marsh | gold 11 | hp 20 | energy 15 | +6 min
  new rows: {"npcs": {"rows": ["#17 Delphine Warrender"], "writes": [10, 38, 44]}}
  die item:amulet of brass item_count trivial 1=1
  · {"decision": "name_is_a_person", "name": "Delphine Warrender", "by": "ask", "why": "op_person"}
  · {"decision": "refused", "item": {"name": "amulet of brass", "tokens": ["brass", "amulet"], "outcome": null, "taken_unasked": false}}
  · {"decision": "figure_is_listed_person", "hint": "the ragged figure"}
  · {"decision": "figure_referred_back_none_here", "kind": "figure"}
  · {"decision": "filed_at_player_place", "code": "Q", "name": "Delphine Warrender", "was": 1, "now": 1, "why": "talked_about"}
  · {"decision": "pencilled_in", "names": ["Delphine Warrender"]}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Delphine Warrender", "pronouns": "she"}]}
  prose end: you snatch away as you advance. A glance inside reveals a small, exposed amulet of polished brass, the salvager's mark still clinging to it. Delphine's eyes dart, searching for a lie. "In the marsh, just a bit north of here. I swear I didn't know what it was!"

## T72 (16.57s, 0 calls)
  > I lower my knife, tell @Q I mean her no harm, and ask what she saw crawl out of the mud last night.
  at The Salt Marsh | gold 11 | hp 20 | energy 15 | +5 min
  die check:persuasion check success 1d20=15
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Bertram Forester", "why": "Bertram is used to dealing with dangerous creatures. He isn't easily spooked by wor
  · {"decision": "talked_to_and_shown_here", "name": "Delphine Warrender", "place": "L7"}
  · {"decision": "sketch_identity_asked", "name": "Delphine Warrender", "asked": ["J", "B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Delphine Warrender", "evidence": "ops"}
  prose end: ake out any other features before it dove beneath the surface and vanished." Delphine shakes her head. "I'm no lorekeeper, traveler. But the tales say that things lurk in the marsh. Things best left undisturbed. Perhaps you should seek your answers elsewhere."

## T73 (17.89s, 0 calls)
  > I tell @Q to lead me to the Eel Pool where the creature dove, and I wade after her with my knife ready.
  at The Salt Marsh | gold 11 | hp 20 | energy 15 | +6 min
  new rows: {"events": {"rows": ["#6 NAME: The Search for the Eel Pool Creature"], "writes": [13]}}
  die skill:Perception
delta: +1
ATT skill_gain small 1=1
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "reedy", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You wade out further, your blade poised to strike at anything that might lurk beneath the surface."}
  · {"decision": "payout_refused", "quest": "quest:Q2 accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: Delphine says, her voice tight with fear. "Beyond that, the water deepens and the currents are strong. But that's where you'll find what you seek, I'm sure of it." It's cool and slick against your skin, the bottom a silt of unknown depth. You wade out further.

## T74 (14.8s, 0 calls)
  > I wade toward the black shape stirring in the Eel Pool and stab at the eel-thing with my knife.
  at The Salt Marsh | gold 11 | hp 20 | energy 14 | +6 min
  die check:melee check partial 1d20=10
  · {"decision": "attack_found", "target": {"code": "Q", "name": "Delphine Warrender"}, "source": "trigger", "skill": ""}
  · {"decision": "combat_follows_attack_check", "code": "Q", "check_outcome": "partial", "was": "hit", "now": "glancing_hit", "damage": 1}
  · {"decision": "name_is_a_person", "name": "Griselda Stanbury", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  · {"decision": "refused", "item": {"name": "salvage job", "tokens": ["salvage", "job"], "outcome": "unshown_loss"}}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "dagger", "text": "You plunge your dagger in again and again, each stroke bringing you closer to victory."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "dagger", "text": "The tip of your dagger pierces its slime-covered hide, drawing forth a gout of dark blood that tinges the water pink."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You plunge your trusty leather boots into the water and lunge forward, stabbing at the eel-thing with your rusty old blade."}
  prose end: face. "Well struck," she calls out, nodding approvingly. "A fine hit, but you'll need to finish it. They're tough, these eels." The eel-thing fights for its life, but your determination proves too much. With a final, defiant thrash, it goes limp in your grasp.

## T75 (15.86s, 0 calls)
  > I drag the dead eel-thing out of the pool onto the bank and ask @Q to look at it with me and tell me if she has seen its kind before.
  at The Salt Marsh | gold 11 | hp 20 | energy 14 | +5 min
  die skill:'perception' skill_gain small 1=1
  die check:persuasion check failure 1d20=5
  · {"decision": "absent_not_an_opponent", "names": ["Bertram Forester"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "cautious", "person": "Delphine Warrender", "why": "Delphine is curious and open-minded, having encountered many strange creatures 
  · {"decision": "speech_said_before_dropped", "lines": ["\"Well struck, but you'll need to finish it. They're tough, these eels,\" she notes, eyeing the creature as if searching f"]}
  · {"decision": "name_is_a_person", "name": "Everard Wadley", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  prose end: he might have some insight into this strange creature. Delphine thinks for a moment, then shakes her head. "No, I don't recall seeing anything quite so... large and unusual in any of the other pools. But the marshes are vast and full of wonders - and dangers."

## T76 (13.71s, 0 calls)
  > I kneel by the dead eel-thing and search it with my knife, cutting open its belly and checking its mouth for anything it swallowed.
  at The Salt Marsh | gold 11 | hp 20 | energy 14 | +15 min
  die check:perception check failure 1d20=3
  · {"decision": "absent_not_an_opponent", "names": ["Bertram Forester"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "stays_as_shown", "place": "The Salt Marsh", "status": "not_travel"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You crouch by the eel-thing, its corpse pale as the sky, and cut open its belly with your hunting blade."}
  prose end: ries across the exposed flats. You crouch by the eel-thing, its corpse pale as the sky. Your fingers probe the creature's jaws, but there's nothing to find. The eel-thing swallowed nothing. Delphine pauses in her work and watches you curiously as you stand up.

## T77 (19.3s, 0 calls)
  > I ask @Q if she would help me haul the eel-thing to the guild yard so Eadric can see what came out of the marsh.
  at The Salt Marsh -> The Guild Yard | gold 11 | hp 20 | energy 14 | +5 min
  new rows: {"locations": {"rows": ["#10 The Guild Yard"], "writes": [9, 10, 18]}}
  die check:persuasion check success 1d20=16
  · {"decision": "absent_not_an_opponent", "names": ["Bertram Forester"], "named_in_line": true}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Delphine Warrender", "why": "Delphine has no strong objection to helping, but is hesitant about dealing with 
  · {"decision": "name_is_a_person", "name": "Delphine", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "civic_building_requested", "place": "The Guild Yard", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Guild Yard"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_requested", "answer": "still in The Salt Marsh", "destination": "The Guild Yard"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  prose end: nything quite so... large and unusual. There are all sorts of strange creatures out there, but this is different." She looks at you expectantly, waiting to see what you will do next. The eel-thing lies motionless in the mud, waiting for its fate to be decided.

## T78 (19.65s, 0 calls)
  > I look around and say I am still at the marsh, not the guild yard. I lead @Q to the dead eel on the bank and ask her to help me lift it onto my back.
  at The Guild Yard | gold 11 | hp 20 | energy 14 | +5 min
  new rows: {"locations": {"rows": ["#11 The marsh"], "writes": [14]}, "gm_events": {"rows": ["#12 A delayed consequence of recent public actions continues off-screen."], "writes": [27]}}
  die check:persuasion check success 1d20=9
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Delphine Warrender", "why": "A few other herb gatherers might help, but most are too busy or uninterested in 
  · {"decision": "place_bound_by_reference", "code": "L7", "place": "The Salt Marsh", "words": "the marsh"}
  · {"decision": "common_noun_names_known_place", "noun": "marsh", "place": "The Salt Marsh"}
  prose end: der [[Q]] looks at you with a mix of curiosity and caution. She's still crouched by the patch of green plants she was harvesting when you approached. "You're not at the guild yard," she remarks, glancing around at the marshy ground. "What brings you out here?"

## T79 (13.92s, 0 calls)
  > I give up on hauling it, shoulder my pack and head to #L1, Saltmarrow, to find the tallyman.
  at The Guild Yard -> to Saltmarrow | gold 11 -> 26 | hp 20 | energy 11 | +25 min
  new rows: {"npcs": {"rows": ["#18 Payne"], "writes": [15, 45]}, "locations": {"rows": ["#12 to Saltmarrow"], "writes": [10, 11, 14]}}
  die check:athletics check success 1d20=12
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "quote_not_said_by_a_person", "quote": "Good day to be out, traveler,"}
  · {"decision": "where_ended_disagrees", "status": "model", "rule": "", "answer": "in Saltmarrow, outside The Guild Yard", "destination": ""}
  · {"decision": "new_place_in_town", "place": "to Saltmarrow", "town": "Saltmarrow"}
  · {"decision": "quote_seeds_no_one", "quote": "Good day to be out, traveler,"}
  · {"decision": "paid", "quest": "Q2", "action": "step_done", "paid": {"gold": 15, "xp": 25, "karma": 0, "items": [], "units": 1, "text": "+15 gold, +25 XP", "settled": 15, "source": "parser"}, "quote": "The Guild Yard [[L1
  · {"decision": "pencilled_in", "names": ["Payne"]}
  prose end:  called out. "The flats are generous this tide." You grunted in acknowledgment and kept walking, the cobbled streets of Saltmarrow [[L1]] looming ahead. The Guild Yard [[L10]] would still be there when you returned. For now, you had business with the tallyman.

## T80 (10.4s, 0 calls)
  > I walk into Saltmarrow and stop at the Saltmarrow Store, then put two copper on the counter and ask Stephen for a loaf of bread.
  at to Saltmarrow -> Saltmarrow Store | gold 26 | hp 20 | energy 11 | +5 min
  coins in prose: ['two copper', 'Two copper', 'Two copper']
  die item:loaf of bread item_count small 1=1
  die check:persuasion check success 1d20=11
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "This is a normal, polite request for a common item at a store. Most people, including the character, would
  · {"decision": "quote_said_by_a_person", "quote": "A loaf of bread, please. Two copper."}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_enter", "answer": "still in to Saltmarrow", "destination": "Saltmarrow Store"}
  · {"decision": "refused", "item": {"name": "loaf of bread", "tokens": ["loaf", "bread"], "outcome": null, "taken_unasked": false}}
  prose end: nd. Behind it stands a man in worn trader's garb, his eyes wary. "Bread," you ask him. "A loaf of bread, please. Two copper." He nods curtly. "Two copper will get you a loaf, but there's no guarantee it won't be moldy. Saltmarrow's not known for its bakeries."

## T81 (14.3s, 0 calls)
  > I slide the two copper across the counter, take the loaf, and ask @E whether Eadric has been in today.
  at Saltmarrow Store | gold 26 | hp 20 | energy 11 | +5 min
  coins in prose: ['two copper']
  die check:persuasion check failure 1d20=5
  · {"decision": "absent_not_an_opponent", "names": ["= Marcella"], "named_in_line": true}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Stephen", "why": "The player is acting in character for a trader, who would likely be more likely to hand ove
  · {"decision": "name_is_a_person", "name": "Humphrey Penhallow", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "loaf", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Store", "status": "not_travel"}
  prose end: en in today. Stephen [[E]] frowns slightly. "Captain Eadric? He was here a couple of tides ago, but I haven't laid eyes on him since." The trader wipes his hands on his apron. "You're not looking for trouble, are you? Eadric's a man who keeps his own counsel."

## T82 (10.47s, 0 calls)
  > I thank Stephen, eat some of the bread, and head to #L9, the salvage yard, to find @F.
  at Saltmarrow Store -> Saltmarrow Salvage Yard | gold 26 | hp 20 | energy 12 | +20 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "glimpse", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "new_location", "answer": "outside Saltmarrow, on the road or in the wilds", "destination": "Saltmarrow Salvage Yard"}
  · {"decision": "figure_is_listed_person", "hint": "a figure"}
  prose end: er a while, you catch a glimpse of the salvaged boat in the distance, its metal frame half-buried in the sand. As you approach, you spot a figure standing near the entrance to the salvage yard, hunched over and shivering in the cold. It's Captain Eadric [[F]].

## T83 (16.6s, 0 calls)
  > I tell @F plainly: I brought the salvage you asked for, so mark my job complete and pay me the fifteen gold.
  at Saltmarrow Salvage Yard | gold 26 -> 41 | hp 20 | energy 13 | +6 min
  die check:persuasion check partial 1d20=6
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Eadric", "why": "A few crew members might try to cheat the Captain out of their pay, but most would not openl
  · {"decision": "name_is_a_person", "name": "Simon Everly", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "not_travel"}
  · {"decision": "refused", "item": {"name": "silver", "tokens": ["silver"], "outcome": "unshown_loss"}}
  · {"decision": "settled", "detail": {"source": "offer_unanswered", "offer": 15, "gold_delta": 0}}
  · {"decision": "paid", "quest": "Q1", "action": "step_done", "paid": {"gold": 15, "xp": 25, "karma": 0, "items": [], "units": 1, "text": "+15 gold, +25 XP", "settled": 15, "source": "parser"}, "quote": "The captain of the 
  prose end: n of the guild knows you've brought back what Eadric [[F]] asked for - a haul from the exposed coastal shallows at the wrong tide. "I see you've returned with the goods," he remarks dryly. "You're looking for your pay and to mark the job delivered, I presume?"

## T84 (16.33s, 0 calls)
  > I hold out my hand and say: Eadric, I heard you say the job is done. Hand me the coin you owe, and mark the second job, the delivery, complete too.
  at Saltmarrow Salvage Yard | gold 41 -> 158 | hp 20 | energy 13 | +6 min
  die player.gold_delta 6d20+60=117 (turn_bands)
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "offer_names_no_task", "title": "Completing two jobs", "line": "Alright Isk, I said the job's done. Here's the coin for the first job, and the mark that it's delivered. Second job's complete too, Another fif
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "complete", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "sketch_faded", "name": "Payne", "made": 81, "unmentioned_turns": 5}
  prose end: . Here's the coin for the first job, and the mark that it's delivered." He tosses a leather pouch into your hand and moves to the ledger, making a quick X next to your name. "Second job's complete too," he calls over his shoulder. "Another fifty in the pouch."

## T85 (17.11s, 0 calls)
  > I count the pouch in front of Eadric, tell him how much I make it, and ask him to tell me aloud which jobs are now closed in his ledger.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 13 | +5 min
  die player.gold_delta 4d10+12=-47 (turn_bands)
  die check:persuasion check success 1d20=10
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "dismissive", "person": "Eadric", "why": "The player is following the rules and protocol for the game's mechanics."}
  · {"decision": "speech_said_before_dropped", "lines": ["\"Alright Isk, I said the job's done. Here's the coin for the first job, and the mark that it's delivered.\""]}
  · {"decision": "unshown_named_move_dropped", "destination": "Coast Road", "line": "i count the pouch in front of eadric, tell him how much i make it, and ask him to tell me aloud which jobs are now closed in his ledger."}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside Saltmarrow Salvage Yard", "confirm": "Yes, you are"}
  · {"decision": "refused", "item": {"name": "brass token", "tokens": ["brass", "token"], "outcome": null, "taken_unasked": false}}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: ob is marked. Ledger's closed on both." He pushes a brass token across the table to you. "This marks the jobs done." Eadric [[F]] nods. "Aye. Out on the tidelands at dawn, then. Don't be late." Eadric [[F]] watches you walk out, then turns back to his ledgers.

## T86 (12.6s, 0 calls)
  > I use Tidecount to feel when the flats will next drain, so I know when I can go out on the tidelands.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 12 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "moment", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside Saltmarrow Salvage Yard", "confirm": "Yes, you are"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "tide-reckoner", "quantity": 1}
  · {"decision": "owned_item_not_new", "item": "tide-reckoner", "owned": "mother's brass tide-reckoner"}
  prose end: r as you make your way across the exposed mudflats. You take a moment to steel yourself, the weight of your debt and the promise of salvage on your mind. With a final check of the tide-reckoner, you rise to your feet, ready to step out onto the shifting sands.

## T87 (12.84s, 0 calls)
  > I take twenty gold from the pouch, set it on Eadric's ledger, and tell him it goes against the winter credit I owe the guild.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 12 | +6 min
  new rows: {"gm_events": {"rows": ["#13 Private note for later: Eadric marks the jobs done and locks the ledger."], "writes": [13]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "speech_said_before_dropped", "lines": ["\"The second job is marked. Ledger's closed on both.\"", "\"This marks the jobs done,\" he says, locking it.", "\"Aye. Out on the tidelands at dawn, then. Don't be la
  · {"decision": "unshown_named_move_dropped", "destination": "Coast Road", "line": "i take twenty gold from the pouch, set it on eadric's ledger, and tell him it goes against the winter credit i owe the guild."}
  · {"decision": "gain_without_coin_dropped", "stated": 20, "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  prose end: say. Eadric [[F]] pockets the gold, then closes the ledger. The steady morning mist hangs heavy in the air. Saltmarrow lies just beyond, the heart of the salvage guild's operations. You've got a few hours to kill before the tide turns and the real work begins.

## T88 (20.91s, 0 calls)
  > I leave the yard and head to #L1, into the heart of Saltmarrow, looking for someone I have not spoken to yet.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 12 | +6 min
  new rows: {"events": {"rows": ["#7 title="], "writes": [18]}, "gm_events": {"rows": ["#14 Consider the options carefully before making a decision."], "writes": [19]}}
  die item:brass item_count trivial 1=1
  die item:brass item_count trivial 1=1
  die skill:name= skill_gain small 1=1
  die check:perception check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "NAME=", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "loose", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_via", "answer": "at Coast Road", "destination": "Saltmarrow Salvage Yard"}
  · {"decision": "person_not_place", "name": "name="}
  · {"decision": "refused", "item": {"name": "brass", "tokens": ["brass"], "outcome": "gain", "taken_unasked": true}}
  · {"decision": "refused", "item": {"name": "brass", "tokens": ["brass"], "outcome": "unshown_loss"}}
  prose end: passing the ruined lower district. The coastal flats are still flooded. The tide will be out for a few more hours. You see a few other people on the streets, but none you know yet. Eventually, you find yourself at the coast road. The lighthouse looms over you.

## T89 (10.69s, 0 calls)
  > I stop at the old lighthouse and call up to @D, asking Elric if he has anyone new staying with him.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 12 | +6 min
  die check:persuasion check success 1d20=17
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "The request is neutral and reasonable. There's no reason for most people to refuse."}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "not_travel"}
  prose end:  the horizon. The lighthouse stands tall against the sky, its beam sweeping over the flats. Elric [[D]]'s gaze turns inquiring. "I haven't had any new... guests staying with me," he says. "Though that could change at any moment. The flats are a popular place."

## T90 (16.26s, 0 calls)
  > I ask @D to mark my salvage job done in his own book and pay me what the reeve owes me for it, plainly.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 12 | +5 min
  die check:persuasion check failure 1d20=2
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Elric", "why": "A few workers might refuse, as they are already paid and marking it as done could anger the r
  · {"decision": "speech_said_before_dropped", "lines": ["\"What brings you to my yard this fine - if 'fine' may be a generous term for this weather.\""]}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "not_travel"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: sy for you either. "Very well," he says at last, nodding slowly. "I'll make note of your work and settle up with the reeve. But you'll need to wait for him to return - I can't pay out of my own purse." He turns and gestures for you to follow him to the office.

## T91 (7.41s, 0 calls)
  > I follow @D into the office and wait there for the reeve to come back, keeping my hand on my pouch.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 13 | +15 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Followed @D with no place named; the player stayed in Saltmarrow Salvage Yard."}
  prose end:  of his desk. "I shan't be long." You remain standing, tense and alert. The office is cramped and filled with the scent of salt and old documents. Piles of papers and ledgers cover every surface. You can hear the soft sound of waves lapping outside the window.

## T92 (27.12s, 0 calls)
  > !wait 60 wait
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 16 | +60 min
  new rows: {"npcs": {"rows": ["#19 Edmund"], "writes": [4, 11, 15]}, "events": {"rows": ["#8 Fight Breaks Out"], "writes": [17]}}
  die skill:Insight skill_gain trivial 1=1
  · {"decision": "name_is_a_person", "name": "Orabel Tapley", "by": "ask", "why": "op_person"}
  · {"decision": "model_move_dropped", "destination": "The Drowned Lower District [[L4]]", "why": "not_a_place"}
  prose end: es. A crowd gathers, and a hush falls over the yard as the two men continue to struggle. Elric [[D]] looks over at you and nods. "It seems our friend has found himself some trouble," he remarks with a wry smile. "Shall we step in, or let fate take its course?"

## T93 (13.19s, 0 calls)
  > I draw my knife and shout at the man in tattered robes to let go of @R, ready to stab him if he does not.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 15 | +6 min
  die check:melee check partial 1d20=7
  · {"decision": "attack_found", "target": {"code": "D", "name": "Elric"}, "source": "trigger", "skill": ""}
  · {"decision": "speech_said_before_dropped", "lines": ["\"Ah, it grows late,\" he says.", "\"You should find a place to rest, if you plan to stay in Saltmarrow. It seems our friend has found himself some trouble."]}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "unresolved"}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: . "And what, pray tell, is your price for this 'help'?" Isk smiles slightly. "I think we can come to an arrangement," she says. "But let's start by discussing the problem at hand, shall we?" Elric [[D]] nods. "Very well," he says. "Let's talk about the tides."

## T94 (14.5s, 0 calls)
  > I turn on the robed man in the office doorway and stab at him again, this time ignoring Elric.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 13 | +6 min
  die check:melee check partial 1d20=8
  · {"decision": "attack_found", "target": {"code": "D", "name": "Elric"}, "source": "trigger", "skill": ""}
  · {"decision": "noun_is_no_figure", "kind": "shout", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "gap", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "Saltmarrow Salvage Yard", "status": "not_travel"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "The man stumbles back, clutching at his arm where your blade nicked the sleeve."}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  prose end: de, heart pounding. It's dark in here and you can't tell if you're alone. You back against the wall, gasping for breath. The door bangs open and you freeze. "Come out with your hands up," a voice commands. It's Elric [[D]]. "You're not getting away with this."

## T95 (12.76s, 0 calls)
  > I step out of the shack with my hands open and tell @D I struck at the robed man, not at him, and I am sorry the blow landed on him.
  at Saltmarrow Salvage Yard | gold 158 | hp 20 | energy 13 | +6 min
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "server_move_not_shown", "destination": "Saltmarrow", "rule": "venue_exit"}
  · {"decision": "figure_is_listed_person", "hint": "the cloaked fellow"}
  · {"decision": "figure_referred_back_none_here", "kind": "fellow"}
  prose end: Elric [[D]] cuts you off. "Now, I've no time for more of your meddling. Leave off or I'll have you arrested for trespassing." He stalks away. You watch him go. You're running out of chances to find out what's really going on with the dead and the salvage here.

## T96 (8.31s, 0 calls)
  > I walk away from the yard and head to #L1, Saltmarrow, to see if @B is at her post and tell her what has happened.
  at Saltmarrow Salvage Yard -> Saltmarrow | gold 158 | hp 20 | energy 13 | +6 min
  new rows: {"events": {"rows": ["#9 the watchmen react to you"], "writes": [11, 13]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "quote_said_by_a_person", "quote": "Hey! Hold up there. You wouldn't happen to be the one who made it out of the yar"}
  prose end:  and smoking pipes just outside the walls. As you pass by, one of them calls out to you. "Hey! Hold up there. You wouldn't happen to be the one who made it out of the yard alive, would you?" the watchmen asks, stepping in your path. "We've been expecting you."

## T97 (8.9s, 0 calls)
  > I stop and tell the watchman I am Isk Tarrow, a flat-runner born in this town, and ask what he wants with me and what his name is.
  at Saltmarrow | gold 158 | hp 20 | energy 13 | +5 min
  new rows: {"npcs": {"rows": ["#20 Cully ROLE="], "writes": [11, 27, 31]}}
  die check:persuasion check success 1d20=18
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few locals might recognize Isk Tarrow, but most would not have the authority to question him."}
  · {"decision": "name_is_a_person", "name": "Cully ROLE=", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "placed_in_scene", "name": "Cully ROLE=", "unknown_place": "[[L1]]", "place": "L1"}
  · {"decision": "pencilled_in", "names": ["Cully ROLE="]}
  prose end: ome again, or whatever you call it when a flat-runner shows up in the streets." The younger watchmen, lean and eager, steps forward. "I'm Cully. Never heard of you, but we watchmen look out for the runners. What brings you to Saltmarrow now?" The name is Time.

## T98 (13.13s, 0 calls)
  > I tell the veteran that I owe the guild, am heading to the tavern, and ask if a runner named Lettice Orme has passed through, then I ask what he means by expecting me.
  at Saltmarrow | gold 158 | hp 20 | energy 13 | +5 min
  die check:persuasion check success 1d20=16
  · {"decision": "absent_not_an_opponent", "names": ["Person 1"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Lettice Orme", "why": "The veteran may have limited information about the runner's movements."}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "unresolved"}
  · {"decision": "role_kept", "name": "Lettice Orme", "kept": "message runner", "given": "runner"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: hrug. "The guild don't forget. But we ain't here to collect. You're heading to the tavern? There's a runner named Orme, name of... Lettice Orme [[B]]... You said?" He raises an eyebrow. "Expecting me? Not sure what you mean by that. I ain't asked for nothing."

## T99 (6.74s, 0 calls)
  > I walk through the gate toward the quay, looking for @B, and sit down on a crate at the water's edge to wait for the tide to turn.
  at Saltmarrow -> The Quay | gold 158 | hp 20 | energy 16 | +360 min
  new rows: {"locations": {"rows": ["#13 The Quay"], "writes": [6, 7, 12]}}
  die check:perception check partial 1d20=7
  · {"decision": "absent_not_an_opponent", "names": ["Person 1"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "open_quote_closed", "paragraphs": ["\"Ah\""]}
  · {"decision": "walk_inside_another_intent", "primary": "investigation", "destination": "(new place)"}
  · {"decision": "outdoor_area_requested", "place": "The Quay", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Quay"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_requested", "answer": "still in Saltmarrow", "destination": "The Quay"}
  prose end: . As you approach, she turns and smiles. "Hello there," she calls out. "I've been waiting for the tide. It's not safe to cross to the island until it comes in a bit higher." Lettice joins you, resting a foot on the crate and continuing to watch the water. "Ah"

## T100 (7.35s, 0 calls)
  > I sit beside Lettice, tell her about my mother and the tide-reckoner that never keeps true time, and ask her if she will walk the flats with me at the next dry tide.
  at The Quay | gold 158 | hp 20 | energy 16 | +5 min
  die check:persuasion check success 1d20=19
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few might feel uncomfortable discussing personal matters so openly with someone they just met."}
  · {"decision": "stays_as_shown", "place": "The Quay", "status": "unresolved"}
  · {"decision": "unfinished_tail_repaired", "why": "unfinished_tail", "text": "As you talk, a few other figures move at the edges of The Qu"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: e flats with me at the next dry tide?" Lettice smiles slightly and says, "I suppose I have time. The next tide won't be dry for days yet. But I don't much like the flats. Too many memories of my father, out there collecting salt. I'd rather stay here in town."

100 turns: median 14.5s mean 14.8s max 27.1s; model calls median 0.0
