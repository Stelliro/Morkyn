
## T1 (17.17s, 0 calls)
  > I ask the tallyman at the flats what I owe him for the winter, and whether there is any work going.
  at Saltmarrow | gold 12 | hp 20 | energy 16 | +5 min
  new rows: {"npcs": {"rows": ["#1 Mattias"], "writes": [11, 31]}}
  die check:persuasion check success 1d20=16
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "The tallyman is likely to be more forthcoming with a winter bill and work compared to an ordinary person.
  · {"decision": "name_is_a_person", "name": "Quentin Tully", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "unresolved"}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Mattias"]}
  prose end: over the fields, then back at you. "The winter's been hard. Most of the work's already been spoken for. But if you're willing to work, I might have something. A few of the farms could use a hand with repairs and maintenance. The pay is small, but it's steady."

## T2 (24.13s, 0 calls)
  > I accept the repair work and ask how much it pays, and what exactly he wants me to do first.
  at Saltmarrow | gold 12 | hp 20 | energy 14 | +15 min
  new rows: {"npcs": {"rows": ["#2 Man 1"], "writes": [6, 14, 15, 48]}, "quests": {"rows": ["#1 Patch Water Trough Leak"], "writes": [41, 42, 43, 46]}, "quest_steps": {"rows": ["#1 patch up a leaking water trough out back"], "writes": [44]}}
  coins in prose: ['five silver', 'five silver']
  die check:persuasion check partial 1d20=2
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Mattias", "why": "Most toll keepers would accept the repair work and negotiate pay and tasks, as it benefits 
  · {"decision": "name_is_a_person", "name": "Percival Stanbury", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Osbert Sadler", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Idony Oakes", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Gisela Lowther", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Piers Padgett", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "gain_without_coin_dropped", "stated": 5, "why": "the prose shows no coin reaching the player"}
  · {"decision": "repeated_grant_dropped", "item": "toolkit", "via": "take_read_as_gain"}
  · {"decision": "refused", "item": {"name": "toolkit", "tokens": ["toolkit"], "outcome": null, "taken_unasked": false}}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "checked_offer_kept", "title": "Patch Water Trough Leak", "keyword_verdict": "no_offer_in_exchange"}
  · {"decision": "taken_on_offer", "quest": "Q1", "title": "Patch Water Trough Leak"}
  · {"decision": "pencilled_in", "names": ["Man 1"]}
  prose end: . "I can pay you five silver for the oven door, and ten for the sign. I'll need them done by noon today if you can manage it." "Well, besides those two, I've got a water trough out back that's leaking. If you can patch it up, I'll pay you another five silver."

## T3 (18.61s, 0 calls)
  > I agree to patch the water trough for the five silver and go out back to look at the leak.
  at Saltmarrow -> Back Stable Yard | gold 12 | hp 20 | energy 13 | +6 min
  new rows: {"locations": {"rows": ["#2 Back Stable Yard"], "writes": [12, 13, 14]}}
  coins in prose: ['five silver']
  die player.gold_delta 2d6+3=-15 (turn_bands)
  die item:leak item_count small 1=1
  · {"decision": "name_is_a_person", "name": "Egbert Langley", "by": "ask", "why": "op_person"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "leak", "quantity": 1}
  · {"decision": "loss_not_shown", "gold_delta": -15, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "refused", "item": {"name": "leak", "tokens": ["leak"], "outcome": null, "taken_unasked": false}}
  · {"decision": "spend_voided", "detail": true}
  prose end: see it. There's nothing more to do here. The silver from the trough patch will buy you a hearty meal and a cup of ale to start your day. With a satisfied nod, you turn and retrace your steps through the stable yard, ready to face whatever the day has in store.

## T4 (10.35s, 0 calls)
  > I walk back to Dale, tell him the trough is patched, and ask him for my five silver.
  at Back Stable Yard -> The Dale | gold 12 -> 27 | hp 20 | energy 13 | +5 min
  new rows: {"npcs": {"rows": ["#3 Dale"], "writes": [15, 40]}, "locations": {"rows": ["#3 The Dale"], "writes": [6, 7, 12]}}
  die check:persuasion check partial 1d20=7
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "", "person": "", "why": "A skilled character would return to their companion after completing a task and request payment as expecte
  · {"decision": "name_is_a_person", "name": "Dale", "by": "ask", "why": "prose"}
  · {"decision": "named_building_requested", "place": "The Dale", "kind": "", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Dale"}
  · {"decision": "where_ended_disagrees", "status": "repaired", "rule": "venue_requested", "answer": "still in Back Stable Yard", "destination": "The Dale"}
  · {"decision": "model_reward_dropped", "quests": [1], "fields": ["gold_delta"], "why": "the quest parser finishes and pays this job"}
  · {"decision": "model_reward_dropped_for_quest_payout", "fields": ["gold_delta"]}
  · {"decision": "introduced_in_prose", "name": "Dale", "role": "swineherd"}
  · {"decision": "paid", "quest": "Q1", "action": "step_done", "paid": {"gold": 15, "xp": 25, "karma": 0, "items": [], "units": 1, "text": "+15 gold, +25 XP", "settled": 15, "source": "parser"}, "quote": "You find Dale near 
  · {"decision": "pencilled_in", "names": ["Dale"]}
  prose end: g air. The stable yard is quiet now, with only a few horses still munching hay in their stalls. You find Dale [[C]] near the trough you patched yesterday. "Ah, you're back," Dale [[C]] says with a nod. "The trough is patched well. You've done good work there."

## T5 (23.51s, 0 calls)
  > I head out to the shore of the flats to look for whatever beast has been prowling the marsh.
  at The Dale -> The Shore | gold 27 | hp 20 | energy 13 | +6 min
  new rows: {"locations": {"rows": ["#4 The Shore"], "writes": [6, 7, 14]}}
  die skill:tracking skill_gain small 1=1
  die check:perception check success 1d20=18
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Bryony Orme", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "investigation", "destination": "(new place)"}
  · {"decision": "outdoor_area_requested", "place": "The Shore", "made": true}
  · {"decision": "left_for_named_place", "left": "The Dale", "destination": "The Shore"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "wolf", "quantity": 1}
  · {"decision": "refused", "item": {"name": "wolf", "tokens": ["wolf"], "outcome": null, "taken_unasked": false}}
  prose end: ath of hardened earth cuts through the marsh, leading to the distant shore. You follow it, boots squelching in the damp soil. The sun is just rising, casting a golden glow over the scene. As you walk, you scan the tall grasses, alert for any sign of the beast.

## T6 (9.74s, 0 calls)
  > I crouch among the reeds and search the mud for tracks, listening for the beast.
  at The Shore | gold 27 | hp 20 | energy 12 | +15 min
  new rows: {"locations": {"rows": ["#5 The marshes."], "writes": [10, 28]}}
  die check:perception check partial 1d20=13
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes"}
  · {"decision": "sketch_faded", "name": "Mattias", "made": 2, "unmentioned_turns": 5}
  prose end:  been eluding you. The reeds sway gently in the breeze, providing a natural barrier between you and whatever dangers may lurk in the marshes. The sound of the boat grows fainter, and for a moment, you are completely alone, lost in thought and the task at hand.

## T7 (8.98s, 0 calls)
  > I wade further out toward the deep reeds, knife out, and call out to see if anything answers.
  at The Shore | gold 27 | hp 20 | energy 12 | +6 min
  new rows: {"npcs": {"rows": ["#4 Figure 1"], "writes": [10, 11, 37, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57]}, "gm_events": {"rows": ["#1 Figure 1 pursues private business that may matter later."], "writes": [30]}}
  · {"decision": "retold_sentences_dropped", "sentences": ["The shore [[L4]] is empty, but then a rustle sounds from the reeds.", "An old woman with a long grey braid emerges."]}
  · {"decision": "noun_is_no_figure", "kind": "rustle", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Looking for something, traveler?"}
  · {"decision": "stays_as_shown", "place": "The Shore", "status": "not_travel"}
  · {"decision": "pencilled_in", "names": ["Figure 1"]}
  · {"decision": "sketch_faded", "name": "Man 1", "made": 3, "unmentioned_turns": 5}
  prose end: ure steps out - an old woman with a long grey braid. She looks you up and down, then speaks. "Looking for something, traveler?" You wade further out toward the deep reeds, knife out, and call out to see if anything answers. She eyes you warily before speaking.

## T8 (19.44s, 0 calls)
  > I ask the old woman if she has seen a beast out here, and tell her I carry no coin to waste but can pay a copper for news.
  at The Shore | gold 27 | hp 20 | energy 12 | +5 min
  die check:persuasion check success 1d20=10
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most people in the player's position would be willing to share any relevant information, especially if it
  · {"decision": "noun_is_no_figure", "kind": "pot", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Seen a beast out here?"}
  · {"decision": "stays_as_shown", "place": "The Shore", "status": "not_travel"}
  · {"decision": "figure_referred_back_none_here", "kind": "woman"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "sketch_confirmed", "name": "Figure 1", "evidence": "ops"}
  prose end: them, but none have returned." She pauses, letting the implications hang in the salty sea breeze. "But I'll tell you what I think. I think those beasts are just stories, told by the wind and the waves. There's nothing out there but danger, and a fool's quest."

## T9 (13.37s, 0 calls)
  > I thank her, then follow the tracks deeper into the marsh toward where the scaled things are said to lair.
  at The Shore | gold 27 | hp 20 | energy 12 | +6 min
  die check:survival check success 1d20=18
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "walk_inside_another_intent", "primary": "claim_check", "destination": "(new place)"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Shore", "confirm": "Yes"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "sketch_faded", "name": "Dale", "made": 5, "unmentioned_turns": 5}
  prose end: t on the water. As you pass, one of them calls out a warning about the dangers of the marsh's depths, his voice carrying a hint of concern. You thank him, then continue following the tracks deeper into the marsh toward where the scaled things are said to lair.

## T10 (14.16s, 0 calls)
  > I go on into the deep marsh until I find the lair, bare hands ready, and look for any creature.
  at The Shore -> The Deep Marsh | gold 27 | hp 20 | energy 11 | +6 min
  new rows: {"locations": {"rows": ["#6 The Deep Marsh"], "writes": [6, 7, 19]}}
  die item:clothes item_count trivial 1=1
  die item:shoes item_count trivial 1=1
  die item:bare hands item_count trivial 1=1
  die skill:tracking skill_gain small 1=1
  die check:perception check failure 1d20=7
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "name_is_a_person", "name": "Tamsin Cobb", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "eye", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "disturbance", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "breath", "by": "ask", "first": false, "check": null}
  · {"decision": "walk_inside_another_intent", "primary": "investigation", "destination": "(new place)"}
  · {"decision": "model_move_dropped", "destination": "Saltmarrow [[L1]]", "why": "not_a_place"}
  · {"decision": "outdoor_area_requested", "place": "The Deep Marsh", "made": true}
  · {"decision": "venue_requested_made", "destination": "The Deep Marsh"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "bare hands", "quantity": 1}
  · {"decision": "refused", "item": {"name": "clothes", "tokens": ["clothe"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "shoes", "tokens": ["shoe"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "bare hands", "tokens": ["bare", "hand"], "outcome": null, "taken_unasked": false}}
  prose end: ined to press on despite the potential dangers. The faint sound of dripping water echoes from within the lair, hinting at a dark, damp interior. You take a deep breath and prepare to enter, ready to face whatever challenges await you in the heart of the marsh.

## T11 (11.53s, 0 calls)
  > I step into the lair and look around for the creature that lives here.
  at The Deep Marsh | gold 27 | hp 20 | energy 11 | +6 min
  new rows: {"npcs": {"rows": ["#5 Serpent of Saltmarrow"], "writes": [13, 34]}}
  die item:silver amulet item_count small 1=1
  die skill:SIGIL READING skill_gain small 1=1
  die check:perception check success 1d20=17
  · {"decision": "kind_unread", "name": "Serpent of Saltmarrow", "why": "op_person", "reply": "A place."}
  · {"decision": "noun_is_no_figure", "kind": "sudden", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "The Deep Marsh", "status": "unresolved"}
  · {"decision": "placed_in_scene", "name": "Serpent of Saltmarrow", "unknown_place": "here", "place": "L6"}
  · {"decision": "refused", "item": {"name": "silver amulet", "tokens": ["silver", "amulet"], "outcome": "gain", "taken_unasked": true}}
  · {"decision": "refused_gain_follow_on_trimmed", "item": "silver amulet", "sentence": "The intricate design seems to hold some arcane power, humming faintly as you turn it in your fingers."}
  · {"decision": "refused_gain_follow_on_trimmed", "item": "silver amulet", "sentence": "The shadowy form of a large serpent emerges from the darkness, its yellow eyes glinting with malevolent intelligence as it rears up to 
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Serpent of Saltmarrow"]}
  prose end: aze settles on a glint of metal half-buried in the loamy floor. A sudden rustling from deeper within the lair makes you freeze. You hold your breath, listening intently. The sound grows closer, a slow shuffling step, punctuated by the brush of scales on stone.

## T12 (8.99s, 0 calls)
  > I swing my fist at the creature as it comes out of the dark.
  at The Deep Marsh | gold 27 | hp 19 (-1) | energy 10 | +6 min
  new rows: {"events": {"rows": ["#1 Fending off a night predator"], "writes": [12]}}
  die check:melee check failure 1d20=3
  · {"decision": "stays_as_shown", "place": "The Deep Marsh", "status": "not_travel"}
  prose end: You swing your fist at the creature emerging from the shadows. Your fist connects with the creature's snout with a satisfying thud. The creature howls in pain and staggers back into the darkness. You stand panting, your arm aching from the impact.

## T13 (13.09s, 0 calls)
  > I swing at the creature again, going for its eyes, and shout at it to back off.
  at The Deep Marsh | gold 27 | hp 18 (-1) | energy 10 | +6 min
  new rows: {"events": {"rows": ["#2 Creature Confronted"], "writes": [17]}}
  die skill:bludgeons skill_gain moderate 1d2=1
  die check:melee check failure 1d20=3
  · {"decision": "noun_is_no_figure", "kind": "pass", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_said_by_a_person", "quote": "Easy now, beast! You'll get no more from this one. Back down or I'll put you dow"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Deep Marsh", "confirm": "Yes, you are"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "club", "text": "You swing your club again, aiming for the creature's vulnerable eye sockets."}
  · {"decision": "figure_referred_back_none_here", "kind": "guard"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "sketch_confirmed", "name": "Serpent of Saltmarrow", "evidence": "conversation"}
  prose end: nd tall, catching your breath, and nod back at them. The stable yard and its inhabitants seem to settle back into a new normal, the presence of the creature now just another part of the scene. You wait for your next instructions, ready for whatever comes next.

## T14 (9.36s, 0 calls)
  > I offer the guard two copper for a loaf of bread.
  at The Deep Marsh | gold 27 | hp 18 | energy 9 | +6 min
  new rows: {"npcs": {"rows": ["#6 Olaf"], "writes": [6, 11, 32]}}
  coins in prose: ['two copper', 'Two coppers']
  die player.gold_delta 1d4=-2 (turn_bands)
  · {"decision": "name_is_a_person", "name": "Olaf", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside The Deep Marsh", "confirm": "Yes"}
  · {"decision": "placed_in_scene", "name": "Olaf", "unknown_place": "Saltmarrow's south gate", "place": "L6"}
  · {"decision": "refused", "item": {"name": "loaf of bread", "tokens": ["loaf", "bread"], "outcome": null, "taken_unasked": false}}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "figure_is_one_here", "kind": "guard", "names": ["Olaf"]}
  · {"decision": "pencilled_in", "names": ["Olaf"]}
  prose end: You approach the guard at Saltmarrow [[L1]]'s south gate. He looks you over and then at the two copper you offer him. "Two coppers for a loaf of bread?" he says. "I can get a loaf for a single copper. The marshes are poor hunting grounds these days."

## T15 (12.58s, 0 calls)
  > I use Tidecount to feel when the flats will flood.
  at The Deep Marsh | gold 27 | hp 18 | energy 8 | +6 min
  new rows: {"gm_events": {"rows": ["#2 Serpent of Saltmarrow pursues private business that may matter later."], "writes": [21]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": ""}
  · {"decision": "walk_inside_another_intent", "primary": "inventory", "destination": "(new place)"}
  · {"decision": "stays_as_shown", "place": "The Deep Marsh", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: eepens. The water's pull grows, and she can sense the timing in her jaw. The marsh channels will start to flood in about an hour. The trickles will swell to torrents, filling the low-lying flats first. Isolde's Cove will be cut off from the mainland by midday.

15 turns: median 13.1s mean 14.3s max 24.1s; model calls median 0
