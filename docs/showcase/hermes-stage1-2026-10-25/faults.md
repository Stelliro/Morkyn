
## Stage1 Sonnet player run
| Turn | Severity | Class | What happened (quote the prose / row) | Evidence (trace file) |
|---|---|---|---|---|
| 1 | S2 | speaks for player | "\"I'm looking for work,\" you say. \"What do I owe you for the winter...\"" (narrator voices my line) | turn-001.json |
| 1 | S3 | drift | "rising over the frozen fields", "A few of the farms could use a hand" in a drowned harbour town | turn-001.json |
| 1 | S1 | people | npc row "Mattias" filed while notes say name Quentin Tully; unnamed tallyman | turn-001.json engine.delta.new_rows |
| 2 | S3 | continuity reset | tallyman replaced by shopkeeper "I'm Dale. Welcome to my humble shop" | turn-002.json |
| 2 | S1 | people | named man Dale filed as npc "#2 Man 1" | turn-002.json new_rows |
| 2 | S2 | speaks for player | "You tell him you're looking for repair work, and ask how much it pays." | turn-002.json |
| 3 | S2 | speaks for player | "Once the patch is dry, you wipe your hands on your trousers" - does the job for me; echoes my line verbatim as first sentence | turn-003.json |
| 3 | S3 | drift | harbour flats became "stable yard", "barn", "horses", "trees" | turn-003.json |
| 3 | S1 | dice | gold dice tag player.gold_delta value -15 rolled with no spend; purse stayed 12 (voided) | turn-003.json |
| 4 | S1 | places | location moved to new place row "#3 The Dale" (a person's name) though prose stays at the stable yard trough | turn-004.json LOC |
| 4 | S1 | money | gold 12->27 (+15) with no coin shown in prose; asked for five silver, prose only "You've done good work" (quest paid note) | turn-004.json |
| 4 | S3 | continuity | "the trough you patched yesterday"; Dale now "the swineherd" | turn-004.json |
| 4 | S1 | people | duplicate of Dale: earlier row Man 1 plus Dale #3 (again T2) | turn-004.json |
| 5 | S3 | drift | "lowing of cattle from the farmsteads", "clump of trees", "sun is just rising" (hour: day already a few hours old) | turn-005.json |
| 6 | S1 | places | duplicate place row "#5 The marshes." (trailing period) filed while already at The Shore | turn-006.json new_rows |
| 6 | S2 | agency | "You crouch low, eyes closed, focusing intently ... lost in thought" (decides my posture/state) | turn-006.json |
| 6 | S3 | hour | "The sun is rising" again at T6 (clock turn 6) | turn-006.json |
| 7 | S3 | engine text leak | narration begins "* 850 chars" | turn-007.json |
| 7 | S3 | echo | last paragraph repeats "You wade further out toward the deep reeds, knife out, and call out..." | turn-007.json |
| 7 | S2 | speaks for player | "You call out, \"Hello? Is anyone here?\"" (I wrote no words) | turn-007.json |
| 7 | S1 | people | old woman filed as "Figure 1" (a placeholder noun) plus gm_event "#1 Figure 1 pursues private business that may matter later." | turn-007.json new_rows |
| 8 | S1 | money | prose: "A copper, you say? Very well." purse after.player.gold stays 27 (no copper moved) - known open class | turn-008.json |
| 8 | S2 | speaks for player | "\"But I can pay a copper ... you persist, \"A copper is a lot to spend for a story...\"" - words I never said | turn-008.json |
| 9 | S3 | echo / engine text | last sentence repeats my line; "Saltmarrow's interior is quiet at this early morning hour, 09:09" clock stamped into prose | turn-009.json |
| 9 | S1 | places | prose walks "deeper into the marsh", past fishermen; after.location stays The Shore (travel_unresolved) | turn-009.json |
| 10 | S2 | agency | "You steel yourself and peer inside ... You take a deep breath and prepare to enter" (decides my intent and steps) | turn-010.json |
| 10 | S3 | dice | item_count dice rolled for tags item:clothes, item:shoes, item:bare hands (my own body/clothes) | turn-010.json |
| 11 | S1 | people | npc row "#5 Serpent of Saltmarrow" for an unseen scaled sound; not a numbered Creature row | turn-011.json new_rows |
| 11 | S3 | continuity | "flickering torchlight ... damp stone walls" in a reed-den in a marsh | turn-011.json |
| 12 | S1 | dice | check:melee value 3 band failure, prose "Your fist connects with the creature's snout with a satisfying thud" (outcome contradicts roll) | turn-012.json |
| 12 | S1 | health | player health 20->19 with no wound in prose ("arm aching" only) | turn-012.json |
| 12 | S3 | engine line | no engine attack result line naming creature or damage at all (FIX CHECK 3) | turn-012.json |
| 13 | S3 | drift | lair in the marsh replaced by "the other people in the stable yard - a few workers and a guard"; guard speaks "Easy now, beast!" (again T3 stable yard) | turn-013.json |
| 13 | S2 | agency | "You stand tall, catching your breath, and nod back at them." / "waving your weapon threateningly" (I have no weapon; prose gave me one) | turn-013.json |
| 13 | S1 | dice (again T12) | melee failure 3, prose "your blow connects and it recoils"; health 19->18 unexplained | turn-013.json |
| 14 | S1 | places | prose "You approach the guard at Saltmarrow [[L1]]'s south gate" but after.location stays The Deep Marsh (L6) | turn-014.json |
| 14 | S1 | money (again T8) | two copper offered, guard counters one copper; gold 27 unchanged (spend_voided) | turn-014.json |
| 14 | S1 | people | guard filed as npc "#6 Olaf", a name never in prose | turn-014.json new_rows |
| 15 | S3 | continuity | invented "Isolde's Cove"; "Isk's concentration ... she can sense" third person; "feel ... rising water in your teeth" | turn-015.json |
| 6-15 | S1 | facts | journal fact at T6 "The beast in the marshes has been hunted down and killed." though no beast met | db/turn-010.md journal |
