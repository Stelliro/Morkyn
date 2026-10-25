
## stage2 player faults
| Turn | Severity | Class | What happened (quote the prose / row) | Evidence (trace file) |
|---|---|---|---|---|
| 1 | S1 | money from die | after.player.gold 12 -> 0 though I paid nothing; dice player.gold_delta -27 (turn_bands), note gold purse clamped cost 27. Prose: "You owe me 30 silver for the job." | turn-001 engine.notes |
| 1 | S2 | agency | narrator writes my line as prose: "You greet him and ask how much you owe him, and whether the body job pays in coin." / "You inquire further, \"And the body job...\"" | turns/001.json |
| 4 | S2 | agency | narrator speaks for me: "Trouble's just the price of doing business in Saltmarrow, Reinald. I could use a sharp knife and a reliable partner..." (again T1 class) | turns/004.json |
| 5 | S1 | place name | new place row "#2 to Marsh Edge" (location shown "to Marsh Edge (L2)"): travel word kept in the name | turns/005.json delta.new_rows.locations |
| 6 | S3 | continuity | Reinald [[C]] (with me T5) is not in the T6 scene at all; new unnamed injured man "a hunched figure ... It's a man" has no code and no row (delta empty) | turns/006.json |
| 6 | S2 | agency | "You'll take him there first, then decide what to do." / "Come on. I'll take you somewhere safe." (player speech/decision; engine dropped only part: invented_speech_dropped) | turns/006.json |
| 7 | S1 | people row | new npc row "#4 Jocelin" (op_person) though the prose never names the injured man; he is still "the man" with no code | turns/007.json delta.new_rows.npcs |
| 7 | S3 | continuity/echo | scene resets: "You stand with Reinald [[C]] ... on the edge of the flooded district of Saltmarrow" (I was in the marsh); Reinald's T4 line replayed ("I've got a good blade here that could use the wor...") | turns/007.json |
| 8 | S3 | continuity | companion Reinald [[C]] absent again; op_person name "Walter Lockwood" minted by ask (no row in delta) | turns/008.json |
| 9 | S3 | continuity | Reinald [[C]] (knife grinder who came with me) is re-cast: "It's Reinald [[C]], the deserter you've been trying to track ... I just need to get past Saltmarrow unnoticed" | turns/009.json |
| 10 | S1 | place drift | after.location "Saltmarrow (L1)", delta location "to Marsh Edge (L2)" -> "Saltmarrow (L1)" while the prose is in the reeds with the boar ("The prints lead you deeper into the heart of Saltmarrow.") | turns/010.json delta.location |
| 10 | S3 | identity | Reinald is called "The reeve nods, but keeps his axe out" (he is the knife grinder; Marlow is the reeve); earlier "his axe" | turns/010.json |
| 11 | S1 | FIX A blow at creature | notes: attack_found target {"code":"E","name":"Wat Thatcher"} source "trigger", then combat_follows_attack_check code E damage 2 (glancing_hit) on the NAMED person; only later attack_retargeted E->F (Boar 1) and attack_unresolved_no_line "no combat block or no health on the row". No engine result line in prose. Boar had no row until after the blow | turn-472167e5-000011-player.json |
| 11 | S3 | continuity | "The crowd cheers ... The crowd roars in approval" in an empty marsh; Reinald and Wat Thatcher vanish; new huntswoman Maelis (no row, quote_seeds_no_one) | turns/011.json |
| 11 | S1 | people row | db turn-010: Reinald (C) location_id 2 while player at 1 (companion left behind); Jocelin role "shepherd to" (op text fragment in role); Reinald role "deserter" | db/turn-010.md |
| 12 | S3 | engine text/continuity | prose "an unnamed boar [[F]] in front of you" (row label leaks as "unnamed"); then "Rigor mortis has set in ... it's been dead for a while" for a boar killed the previous turn | turns/012.json |
| 13 | S3 | pronouns | note pronoun_pin_flipped_to_prose name Reinald pronouns "she" evidence {he:0, she:3}: the knife grinder (pinned he at T4) is flipped to she, likely from Maelis sentences | turns/013.json |
| 14 | S1 | blow I never made | my line only led the party out; note attack_found target F Boar 1 source "ask" (reply "Yes, the player is leading Mael..."), dice check:melee 17, engine line inserted: "Your blow hits the boar [[F]]." (note attack_not_in_prose beat) | turn trace turn 14, turns/014.json |
| 14 | S1 | dead creature revived | the boar I killed T11 returns as the same row/code [[F]] ("Boar 1") charging from the reeds; no new row filed | turns/014.json notes figure_is_one_here |
| 14 | S1 | place not updated | prose "The marsh is still and silent ... you wade through the tall grass" but after.location "Saltmarrow" (L1); notes common_noun_names_known_place marsh -> to Marsh Edge but no move | turns/014.json |
| 14 | S2 | agency | "\"We dare not wait for dawn to come,\" you tell them." / "You charge forward." / "You dodge to the side" (player acts decided by narrator) | turns/014.json |
| 15 | S3 | contradicts engine line | engine line "Your blow only grazes the boar [[F]]." then "you dig your knife deeper into its eye socket ... its eye all but destroyed"; boar flees (alive); save: damage 1 only | turns/015.json |
| 15 | S3 | companion kit | Reinald "grips a hunting bow" (T10 "his axe"; T14 "her hands"); Maelis crossbow vs earlier bow | turns/015.json |
