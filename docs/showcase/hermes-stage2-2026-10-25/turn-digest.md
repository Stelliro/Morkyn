
## T1 (16.12s, 0 calls)
  > I greet the tallyman and ask him how much I owe, and whether the body job pays in coin.
  at Saltmarrow | gold 12 -> 0 | hp 20 | energy 16 | +5 min
  coins in prose: ['30 silver', '20 silver', '50 silver']
  die player.gold_delta 4d10+12=-27 (turn_bands)
  die check:persuasion check failure 1d20=6
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "Most tallymen are honest, but a few might try to cheat an adventurer."}
  · {"decision": "quote_not_said_by_a_person", "quote": "Tallyman - Debts Recorded"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "purse", "detail": {"clamped": true, "cost": 27, "purse": 12}}
  · {"decision": "quote_seeds_no_one", "quote": "Tallyman - Debts Recorded"}
  prose end: recorded. That's the standard rate." He pauses, then adds, "Although, if you're looking for more work, I might have something that pays a bit better. A client is looking for a courier to deliver a package across the border, 50 silver and all expenses covered."

## T2 (12.47s, 0 calls)
  > I turn to Reeve Marlow and ask her to come with me to the flooded district, since she wants this done.
  at Saltmarrow | gold 0 | hp 20 | energy 16 | +5 min
  die check:persuasion check failure 1d20=4
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few people might hesitate due to potential danger, but most would likely accompany a trusted party memb
  · {"decision": "quote_said_by_a_person", "quote": "You think I need your help? I'll manage on my own, thank you."}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "unresolved"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: turn to Reeve Marlow and ask her to come with you to the flooded district, since she wants this done. Reeve's eyes narrow at the offer. "You think I need your help? I'll manage on my own, thank you." She crosses her arms, clearly not interested in joining you.

## T3 (12.86s, 0 calls)
  > I look around the guildhall steps for anyone idle who might come along to the flats for a share of the pay, and I ask the nearest person to join me.
  at Saltmarrow | gold 0 | hp 20 | energy 16 | +5 min
  die check:persuasion check success 1d20=14
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few might be hesitant to leave their duties at the guildhall, but most are likely to follow out of curi
  · {"decision": "quote_said_by_a_person", "quote": "You need a grinder?"}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "coin_grant_dropped", "why": "the prose shows no coin reaching the player", "grants": ["silvers"]}
  · {"decision": "figure_referred_back_none_here", "kind": "person"}
  prose end: ats. "I'm looking for someone to help me out, share a bit of pay," you say. "You need a grinder?" he asks, eyeing your worn blade. "Nah, but you might know someone who does. A few silvers in it for the right helper, if you're looking to boost your pay packet."

## T4 (14.73s, 0 calls)
  > I ask the knife grinder his name, and tell him I will split the salvage pay with him if he walks the flats with me today.
  at Saltmarrow | gold 0 | hp 20 | energy 16 | +5 min
  new rows: {"npcs": {"rows": ["#3 Reinald"], "writes": [10, 15, 16, 34, 35, 40]}}
  die check:persuasion check failure 1d20=2
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "", "person": "", "why": "A few knife grinders might be reluctant to leave their work and accompany a stranger on a risky mission f
  · {"decision": "role_was_a_note", "name": "Reinald", "note": "works at South Gate"}
  · {"decision": "name_is_a_person", "name": "Reinald", "by": "ask", "why": "op_person"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "unresolved"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "Split the salvage 50/50 and you can keep your blade sharp and your reputation clean."}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Reinald"]}
  · {"decision": "sketch_identity_asked", "name": "Reinald", "asked": ["B", "A"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Reinald", "evidence": "conversation"}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Reinald", "pronouns": "he"}]}
  prose end: est." Reinald strokes his beard thoughtfully, weighing your offer. "I've got a good blade here that could use the work," he says. "But the flats are no place for an honest man. What kind of salvage are we talking about? And what kind of trouble have you seen?"

## T5 (14.9s, 0 calls)
  > I tell Reinald to come along anyway, and I walk out of town onto the mudflats toward the marsh edge to look for whatever has been dragging bodies about.
  at Saltmarrow -> to Marsh Edge | gold 0 | hp 20 | energy 16 | +6 min
  new rows: {"locations": {"rows": ["#2 to Marsh Edge"], "writes": [10, 11, 14, 35, 55]}}
  die check:perception check partial 1d20=12
  · {"decision": "absent_not_an_opponent", "names": ["Figure 1", "Woman 1"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "name_is_a_person", "name": "Verity Brewster", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Lowen Ilsley", "by": "ask", "why": "op_person"}
  · {"decision": "name_is_a_person", "name": "Anselm Skinner", "by": "ask", "why": "op_person"}
  · {"decision": "walk_inside_another_intent", "primary": "conversation", "destination": "(new place)"}
  · {"decision": "new_place_in_town", "place": "to Marsh Edge", "town": "Saltmarrow"}
  · {"decision": "sketch_faded", "name": "Figure 1", "made": 1, "unmentioned_turns": 5}
  · {"decision": "sketch_faded", "name": "Woman 1", "made": 1, "unmentioned_turns": 5}
  prose end: ies not far off, a dark blur on the horizon where the wetlands begin. You've no idea what might be responsible for the bodies, but someone has been dragging them this way, the trail of blood clearly visible. Reinald [[C]] seems hesitant to follow you out here.

## T6 (15.96s, 0 calls)
  > I crouch and follow the blood trail toward the reeds, looking for the beast that made it.
  at to Marsh Edge | gold 0 | hp 20 | energy 16 | +6 min
  die check:perception check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "noun_is_no_figure", "kind": "trail", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "clearing", "by": "ask", "first": false, "check": null}
  · {"decision": "stays_as_shown", "place": "to Marsh Edge", "status": "unresolved"}
  · {"decision": "take_of_unowned_read_as_gain", "item": "blood trail", "quantity": 1}
  · {"decision": "take_of_unowned_read_as_gain", "item": "reeds", "quantity": 1}
  · {"decision": "refused", "item": {"name": "blood trail", "tokens": ["blood", "trail"], "outcome": null, "taken_unasked": false}}
  · {"decision": "refused", "item": {"name": "reeds", "tokens": ["reed"], "outcome": null, "taken_unasked": false}}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  prose end: ere alone. The marsh is too dangerous. But Saltmarrow [[L1]] is too far. There's a shelter not far from here, a place to rest and think. You'll take him there first, then decide what to do. "Come on. I'll take you somewhere safe. We can figure this out later."

## T7 (17.01s, 0 calls)
  > I ask the injured man what took his crew and which way it went, and I tell Reinald to keep watch behind me.
  at to Marsh Edge | gold 0 | hp 20 | energy 16 | +5 min
  new rows: {"npcs": {"rows": ["#4 Jocelin"], "writes": [6, 8, 15, 18, 21, 45]}, "gm_events": {"rows": ["#1 Off-screen movement continues around to Marsh Edge."], "writes": [37]}}
  die check:persuasion check success 1d20=13
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "trivial", "attitude": "neutral", "person": "Reinald", "why": "The player is just requesting information and keeping Reinald informed, which seems reasonab
  · {"decision": "role_was_a_note", "name": "Jocelin", "note": "works at Marsh Edge"}
  · {"decision": "retold_sentences_dropped", "sentences": ["The fast incoming tide."]}
  · {"decision": "speech_said_before_dropped", "lines": ["\"And what kind of trouble have you gotten yourself into?\"", "\"But what kind of salvage are we talking about?\" he asks."]}
  · {"decision": "open_quote_closed", "paragraphs": ["\"The flooded district, eh?\" Reinald [[C]] says. \"The place is full of things best left undisturbed. But I've got a good blade here that could use the wor...\""]}
  · {"decision": "name_is_a_person", "name": "Jocelin", "by": "ask", "why": "op_person"}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside to Marsh Edge", "confirm": "Yes, you are"}
  · {"decision": "gain_without_coin_dropped", "stated": "none", "why": "the prose shows no coin reaching the player"}
  · {"decision": "settled", "detail": {"source": "gain_without_coin_dropped", "gold_delta": 0, "offer": null}}
  · {"decision": "figure_referred_back_none_here", "kind": "man"}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "pencilled_in", "names": ["Jocelin"]}
  prose end: ast. I made it back to the shore but the rest... they didn't." His voice trails off and you see the haunted look in his bloodshot stare. Reinald [[C]] glances over at you. The wreck out in the shallows. The missing crew. There's something not right about this.

## T8 (10.35s, 0 calls)
  > I wade out through the shallows toward the old wreck, hunting for whatever took the crew.
  at to Marsh Edge | gold 0 | hp 20 | energy 15 | +6 min
  die player.gold_delta 4d10+12=-38 (turn_bands)
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "name_is_a_person", "name": "Walter Lockwood", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "sense", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "sound", "by": "ask", "first": false, "check": null}
  · {"decision": "model_move_dropped", "destination": "[[L2]]", "why": "not_a_place"}
  · {"decision": "stays_as_shown", "place": "to Marsh Edge", "status": "not_travel"}
  · {"decision": "loss_not_shown", "gold_delta": -38, "why": "the interpreter's confirmed gold ask found no money leaving the player"}
  · {"decision": "spend_voided", "detail": true}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "sword", "text": "You've got your sword and bow out, senses on high alert as you hunt for whatever or whoever took the salt panner's whole missing
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: to the marsh, vanishing where the tidal flat turns to mud and reeds. As you reach the wreck, you hear a rustling sound from the reeds. You pause and listen intently - it sounds like someone or something is moving through them, maybe 50 meters out in the marsh.

## T9 (16.26s, 0 calls)
  > I creep toward the rustling in the reeds with my knife drawn and call out softly to see what it is.
  at to Marsh Edge | gold 0 | hp 20 | energy 15 | +6 min
  die check:stealth check success 1d20=15
  · {"decision": "absent_not_an_opponent", "names": ["Jocelin"], "named_in_line": false}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "noun_is_no_figure", "kind": "shadow", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_listed_person", "hint": "a figure"}
  · {"decision": "payout_refused", "quest": "'Reinald's Information'", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  prose end: osing stone walls loom in the distance, barely visible through the dense foliage. Reinald [[C]] appears exhausted, his clothes ragged and covered in mud. His eyes dart around, searching for an escape, but he keeps his hands raised, acknowledging your presence.

## T10 (17.88s, 0 calls)
  > I lower my knife, tell Reinald to stay close, and follow the clawed prints deeper into the reeds to find the beast itself.
  at to Marsh Edge -> Saltmarrow | gold 0 | hp 20 | energy 15 | +6 min
  new rows: {"npcs": {"rows": ["#5 Wat Thatcher"], "writes": [9, 17, 43, 49]}}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["C"]}
  · {"decision": "name_is_a_person", "name": "Wat Thatcher", "by": "ask", "why": "op_person"}
  · {"decision": "noun_is_no_figure", "kind": "shape", "by": "ask", "first": false, "check": null}
  · {"decision": "where_ended_not_confirmed", "answer": "in Saltmarrow, outside to Marsh Edge", "confirm": "Yes, you are"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You lower your blade, ready to strike, but hesitate as you get closer."}
  · {"decision": "figure_is_listed_person", "hint": "a figure"}
  · {"decision": "filed_at_player_place", "code": "E", "name": "Wat Thatcher", "was": 2, "now": 1, "why": "filed_here"}
  · {"decision": "payout_refused", "quest": "accept", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["Wat Thatcher"]}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Wat Thatcher", "pronouns": "he"}]}
  prose end: he boar. He nods to you in recognition. "Thought I heard something," he says, eyeing the boar warily. "Best leave it to its meal. It won't harm you." You and Reinald [[C]] exchange looks. The beast is just a normal boar, no threat. No need to chase it further.

## T11 (9.28s, 0 calls)
  > I ignore them and stab at the boar with my knife, aiming for its throat.
  at Saltmarrow | gold 0 | hp 20 | energy 13 | +6 min
  new rows: {"npcs": {"rows": ["#6 Boar 1"], "writes": [1, 16, 17, 20, 21, 46]}}
  die check:melee check partial 1d20=13
  · {"decision": "attack_found", "target": {"code": "E", "name": "Wat Thatcher"}, "source": "trigger", "skill": "", "people": []}
  · {"decision": "combat_follows_attack_check", "code": "E", "check_outcome": "partial", "was": "hit", "now": "glancing_hit", "damage": 2}
  · {"decision": "noun_is_a_figure", "kind": "boar", "by": "ask", "first": true, "check": true}
  · {"decision": "figure_hostile", "kind": "boar"}
  · {"decision": "noun_is_no_figure", "kind": "chance", "by": "ask", "first": false, "check": null}
  · {"decision": "noun_is_no_figure", "kind": "surge", "by": "ask", "first": false, "check": null}
  · {"decision": "quote_not_said_by_a_person", "quote": "Well fought,"}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You stand over the fallen beast, panting and wiping your blade clean on its coarse hair."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "Your blade scores a direct hit and the boar's eyes go wide in shock."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "The boar snorts in outrage as your blade finds its flesh."}
  · {"decision": "quote_seeds_no_one", "quote": "Well fought,"}
  · {"decision": "figure_introduced_by_the", "kind": "boar", "phrase": "The boar", "sentence": "The boar bellows in pain and charges, trying to trample you underfoot."}
  · {"decision": "unnamed_figure_numbered", "name": "Boar 1", "code": "F", "attitude": "hostile", "by": "ask"}
  · {"decision": "pencilled_in", "names": ["Boar 1"]}
  prose end: You survey the crowd of onlookers, your eye catching on a grizzled old huntswoman. She approaches you, her weathered face impassive but her eyes keen. "Well fought," she says gruffly. "I'm Maelis. You've got some potential. Think you're ready for a real hunt?"

## T12 (18.58s, 0 calls)
  > I turn on the huntswoman Maelis and ask her what a real hunt pays, then I tell Reinald to look at the boar and say if it is truly dead.
  at Saltmarrow | gold 0 | hp 20 | energy 13 | +5 min
  new rows: {"npcs": {"rows": ["#7 Maelis"], "writes": [6, 8, 14, 17, 45, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 72]}}
  die skill:animal care skill_gain large 1d2+1=3
  die check:persuasion check success 1d20=13
  · {"decision": "absent_not_an_opponent", "names": ["Wat Thatcher"], "named_in_line": true}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F", "C"]}
  · {"decision": "ask_weight_rated", "weight": "free", "difficulty": "easy", "attitude": "hostile", "person": "Boar 1", "why": "The player's request is reasonable and within the game's rules."}
  · {"decision": "name_is_a_person", "name": "Maelis", "by": "ask", "why": "prose"}
  · {"decision": "figure_does_not_speak", "kind": "boar", "reply": false}
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "meta_leak_repaired", "why": "engine_clock", "count": 1}
  · {"decision": "introduced_in_prose", "name": "Maelis", "role": "huntswoman"}
  · {"decision": "figure_is_one_here", "kind": "boar", "names": ["Boar 1"]}
  · {"decision": "payout_refused", "quest": "Saltmarrow Boar", "reasons": ["unknown_quest", "evidence_not_in_text"], "quote": "", "passive": false}
  · {"decision": "pencilled_in", "names": ["Maelis"]}
  · {"decision": "sketch_faded", "name": "Jocelin", "made": 8, "unmentioned_turns": 5}
  · {"decision": "sketch_confirmed", "name": "Boar 1", "evidence": "ops"}
  · {"decision": "pronouns_pinned_on_first_scene", "pinned": [{"name": "Maelis", "pronouns": "she"}]}
  prose end: its flesh taut and stiff, making the corpse appear almost unnatural in its stillness. Reinald [[C]] approaches the dead animal and examines it, then looks up at you and nods. "It's dead," he says, glancing back at the carcass. "But it's been dead for a while."

## T13 (13.28s, 0 calls)
  > I tell Maelis I will take her hunt, and ask her to lead me and Reinald to the real beast in the marsh.
  at Saltmarrow | gold 0 | hp 20 | energy 13 | +5 min
  die check:persuasion check success 1d20=13
  · {"decision": "absent_not_an_opponent", "names": ["Wat Thatcher"], "named_in_line": true}
  · {"decision": "attack_not_found", "target": null, "source": "ask", "skill": "", "people": ["F", "G", "C"]}
  · {"decision": "ask_weight_rated", "weight": "ordinary", "difficulty": "easy", "attitude": "neutral", "person": "Maelis", "why": "A few skilled hunters might refuse to lead the party, as it's dangerous to leave the real be
  · {"decision": "stays_as_shown", "place": "Saltmarrow", "status": "not_travel"}
  · {"decision": "pronoun_pin_flipped_to_prose", "name": "Reinald", "pronouns": "she", "evidence": {"he": 0, "she": 3}}
  · {"decision": "sketch_identity_asked", "name": "Maelis", "asked": ["E"], "answer": "new", "raw": "{'answer': 'new'}"}
  · {"decision": "sketch_confirmed", "name": "Maelis", "evidence": "prose_code"}
  prose end: But be careful. The marsh is a tricky place, and not all the creatures here are what they seem." The salty breeze rustles through the reeds as she turns to Reinald [[C]]. "We should go at first light tomorrow. The full day will give us time to track and hunt."

## T14 (30.41s, 0 calls)
  > I say we cannot wait for tomorrow: I lead Maelis and Reinald out the gate into the marsh now to find the beast.
  at Saltmarrow | gold 0 | hp 20 | energy 13 | +15 min
  die check:melee check success 1d20=17
  · {"decision": "attack_found", "target": {"code": "F", "name": "Boar 1"}, "source": "ask", "skill": "melee", "people": ["F", "G", "C"]}
  · {"decision": "combat_for_aimed_check", "code": "F", "was": "not_combat"}
  · {"decision": "noun_is_no_figure", "kind": "mist", "by": "ask", "first": false, "check": null}
  · {"decision": "figure_hostile", "kind": "boar"}
  · {"decision": "common_noun_names_known_place", "noun": "marsh", "place": "to Marsh Edge"}
  · {"decision": "common_noun_names_known_place", "noun": "marsh", "place": "to Marsh Edge"}
  · {"decision": "common_noun_names_known_place", "noun": "marsh", "place": "to Marsh Edge"}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "blade", "text": "You charge forward, your blade gleaming."}
  · {"decision": "unowned_weapon_dropped", "why": "unowned_weapon", "weapon": "sword", "text": "You dodge to the side, drawing your sword."}
  · {"decision": "figure_is_one_here", "kind": "boar", "names": ["Boar 1"]}
  prose end: nd pawing at the marsh floor. Its tiny piggy mind seems to be struggling to process your sudden appearance. "Attack it!" Maelis [[G]] commands, aiming her arrow at the boar's head. You charge forward. The boar lets out a furious squeal and charges to meet you!

## T15 (9.68s, 0 calls)
  > I stab at the boar with my knife as it charges, going for its eye, while Maelis and Reinald stand beside me.
  at Saltmarrow | gold 0 | hp 20 | energy 12 | +6 min
  new rows: {"gm_events": {"rows": ["#2 Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present."], "writes": [34]}}
  die check:melee check partial 1d20=12
  · {"decision": "attack_found", "target": {"code": "F", "name": "Boar 1"}, "source": "trigger", "skill": "", "people": []}
  · {"decision": "combat_follows_attack_check", "code": "F", "check_outcome": "partial", "was": "hit", "now": "glancing_hit", "damage": 1}
  · {"decision": "where_ended_not_confirmed", "answer": "outside Saltmarrow, on the road or in the wilds", "confirm": "Yes, you are"}
  · {"decision": "figure_is_one_here", "kind": "boar", "names": ["Boar 1"]}
  · {"decision": "travel_unresolved", "note": "Travel action with no MOVE op and no resolvable destination; player stayed put."}
  · {"decision": "sketch_faded", "name": "Wat Thatcher", "made": 11, "unmentioned_turns": 5}
  prose end: ree from the boar's eye. The enraged creature bolts away into the woods, squealing in pain. Maelis [[G]] and Reinald [[C]] lower their weapons and look to you, breathing hard. "Well done," Maelis [[G]] says with a nod. "It will be blind in that eye, at least."

15 turns: median 14.9s mean 15.3s max 30.4s; model calls median 0
