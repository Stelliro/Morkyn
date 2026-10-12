# World database: turn-050

Exported 2026-10-13T00:46:21 from `world.db` (read-only).

## player (1)

| name | level | xp | gold | health | max_health | energy | max_energy | current_location_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Isk Tarrow | 1 | 32 | 9 | 9 | 20 | 5 | 16 | 10 |

## locations (10)

| id | code | name | kind |
| --- | --- | --- | --- |
| 1 | L1 | Saltmarrow |  |
| 2 | L2 | The Tally House |  |
| 3 | L3 | Philippa Kemp's General Store | general_store |
| 4 | L4 | The Deep Channel |  |
| 5 | L5 | Nearby street |  |
| 6 | L6 | The First Row |  |
| 7 | L7 | The Old Fish Market |  |
| 8 | L8 | The Chimney Roof |  |
| 9 | L9 | The Flooded Rows |  |
| 10 | L10 | The Customs Tower |  |

## npcs (11)

| code | name | role | location_id | attitude | trust | knows_player_name |
| --- | --- | --- | --- | --- | --- | --- |
| A | Philippa Kemp | chandler | 3 | dismissive | 2 | 0 |
| B | Hereward Jessop | clerk | 1 | neutral | 0 | 0 |
| C | Wulfstan | weaver | 1 | neutral | 0 | 0 |
| D | Una Rendle | tally clerk | 2 | neutral | 6 | 0 |
| E | Piers | regular | 2 | neutral | 0 | 0 |
| F | Jocosa Kettle | salvager | 8 | dismissive | 19 | 0 |
| G | Reinald | apprentice | 7 | dismissive | 2 | 0 |
| H | Tam Kemp | carter | 10 | dismissive | 10 | 0 |
| I | Jasper | weaver | 8 | neutral | 0 | 0 |
| J | Ivo | weaver | 10 | neutral | 0 | 0 |
| K | Mara Tarrow | tide-reader | 10 | friendly | 0 | 0 |

## inventory (5)

| name | quantity | item_type | rarity | equipped_slot |
| --- | --- | --- | --- | --- |
| soft-soled boots | 1 | clothing | common | FEET |
| patched tunic | 1 | clothing | common | TORSO |
| wool trousers | 1 | clothing | common | LEGS |
| mother's brass tide-reckoner | 1 | misc | common |  |
| tarred rope | 1 | tool | common |  |

## abilities (1)

| name | locked | cost | power_type |
| --- | --- | --- | --- |
| Tidecount | 0 | 1 energy | soft_cap |

## player_skills (2)

| name |
| --- |
| Salvage |
| Tide Reading |

## quests (1)

| code | title | status | current_step | total_steps | reward_gold | reward_xp |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Raise the customs-house bell | active | 3 | 3 | 30 | 112 |

## quest_steps (3)

| quest_id | step_number | title | status |
| --- | --- | --- | --- |
| 1 | 1 | Sign for the contract | completed |
| 1 | 2 | Reach the old customs house | completed |
| 1 | 3 | Bring the bell back whole | active |

## npc_player_relationships (1)

| npc_id | affinity | fear | respect |
| --- | --- | --- | --- |
| 1 | 5 | 0 | 3 |

## dice_rolls (49)

| turn | tag | kind | band | notation | value | source |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | check:persuasion | check | failure | 1d20 | 3 | skill_check |
| 3 | check:persuasion | check | success | 1d20 | 11 | skill_check |
| 4 | check:persuasion | check | failure | 1d20 | 3 | skill_check |
| 5 | check:persuasion | check | failure | 1d20 | 2 | skill_check |
| 7 | check:persuasion | check | success | 1d20 | 19 | skill_check |
| 8 | check:persuasion | check | success | 1d20 | 14 | skill_check |
| 9 | player.gold_delta | gold | trivial | 1d4 | -2 | turn_bands |
| 9 | item:tarred rope | item_count | small | 1 | 1 | turn_bands |
| 9 | check:persuasion | check | failure | 1d20 | 7 | skill_check |
| 10 | item:tarred rope | item_count | small | 1 | 1 | turn_bands |
| 10 | check:persuasion | check | success | 1d20 | 9 | skill_check |
| 11 | check:persuasion | check | partial | 1d20 | 5 | skill_check |
| 12 | check:survival | check | success | 1d20 | 18 | skill_check |
| 13 | check:athletics | check | failure | 1d20 | 2 | skill_check |
| 14 | check:athletics | check | critical_failure | 1d20 | 1 | skill_check |
| 15 | check:deception | check | failure | 1d20 | 7 | skill_check |
| 16 | check:athletics | check | failure | 1d20 | 3 | skill_check |
| 19 | player.xp_delta | xp | small | 1d6+2 | 8 | turn_bands |
| 19 | check:persuasion | check | critical_success | 1d20 | 20 | skill_check |
| 20 | check:persuasion | check | success | 1d20 | 19 | skill_check |
| 21 | check:persuasion | check | failure | 1d20 | 2 | skill_check |
| 22 | check:persuasion | check | success | 1d20 | 13 | skill_check |
| 23 | check:persuasion | check | success | 1d20 | 13 | skill_check |
| 24 | check:persuasion | check | critical_failure | 1d20 | 1 | skill_check |
| 26 | check:persuasion | check | partial | 1d20 | 10 | skill_check |
| 27 | player.xp_delta | xp | small | 1d6+2 | 3 | turn_bands |
| 27 | check:persuasion | check | success | 1d20 | 18 | skill_check |
| 28 | check:persuasion | check | partial | 1d20 | 7 | skill_check |
| 29 | check:appraise | check | critical_success | 1d20 | 20 | skill_check |
| 30 | check:persuasion | check | failure | 1d20 | 3 | skill_check |
| 32 | check:mining | check | failure | 1d20 | 8 | skill_check |
| 33 | player.health_delta | damage | trivial | 1 | -1 | turn_bands |
| 34 | check:athletics | check | failure | 1d20 | 8 | skill_check |
| 35 | check:athletics | check | critical_failure | 1d20 | 1 | skill_check |
| 37 | check:persuasion | check | partial | 1d20 | 8 | skill_check |
| 38 | check:persuasion | check | success | 1d20 | 9 | skill_check |
| 39 | player.xp_delta | xp | small | 1d6+2 | 5 | turn_bands |
| 39 | check:persuasion | check | success | 1d20 | 12 | skill_check |
| 40 | check:persuasion | check | failure | 1d20 | 2 | skill_check |
| 41 | check:persuasion | check | success | 1d20 | 15 | skill_check |
| 43 | check:persuasion | check | failure | 1d20 | 5 | skill_check |
| 45 | check:persuasion | check | failure | 1d20 | 4 | skill_check |
| 46 | check:persuasion | check | success | 1d20 | 11 | skill_check |
| 47 | player.xp_delta | xp | moderate | 2d6+6 | 16 | turn_bands |
| 47 | check:persuasion | check | success | 1d20 | 15 | skill_check |
| 48 | check:persuasion | check | failure | 1d20 | 5 | skill_check |
| 49 | check:persuasion | check | success | 1d20 | 9 | skill_check |
| 50 | check:persuasion | check | success | 1d20 | 13 | skill_check |
| 51 | check:persuasion | check | partial | 1d20 | 9 | skill_check |

## journal, engine entries (155 of 255)

- T0 `setup` Playthrough started: {"difficulty": "normal", "narration_detail": "balanced", "world_style": "frontier dark fantasy", "custom_style": "A drowned harbour town at the edge of mudflats the sea left behind. Salvage, debt and a tide that keeps the wrong hours.", "leveling_system": true, "game_system": fa
- T0 `system` Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, do not seed default player skills beyond any recorded weak skill seed, and set any model-decided ability costs or prerequisites through ability_updates.
- T0 `backstory` known/known: Isk grew up in Saltmarrow, the harbour town the sea abandoned forty years ago. She runs the exposed flats at dry tide, pulling salvage out of the drowned lower district before the water comes back for a few hours each night. Her mother went out on the flats six years ago and never came 
- T1 `opening` Opening scene: the model introduced the initial situation before the player acted.
- T1 `self_check` {"passed": true, "issues_found": ["npcs creates Hereward Jessop but the narration never names him; the clerk at the tide marks appears only as 'a thin man with a slate'."], "corrections_made": ["Verifier replaced narration.", "Deterministic entity name/code repair applied to narration."], "reference
- T1 `rumor` Philippa Kemp's nephew Tam went out on the flats at the last dry tide with a hand cart and has not come back.
- T1 `fact` The guild posted a coin-paid contract for the bell of the old customs house, furthest out on the flats.
- T2 `self_check` {"passed": true, "issues_found": ["relationships targets code YOU, which is not an entity code in world_state; the player is not an NPC row."], "corrections_made": ["Verifier replaced relationships.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier 
- T2 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T2 `skill_check` You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 3  ·  Base success (DC): 11  ·  vs Philippa Kemp power 9 Result: failure (bad nothing)  ·  margin -8 You do so poorly it is almost as if you had done nothing at all.
- T3 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T3 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T3 `skill_check` You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 11  ·  Base success (DC): 9  ·  vs Philippa Kemp power 7 Result: success (barely)  ·  margin +2 You just barely scrape through.
- T4 `self_check` {"passed": true, "issues_found": ["Hereward says 'a dead woman's clock': nothing in world_state tells him the reckoner's owner is dead."], "corrections_made": ["Verifier replaced narration.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: 
- T4 `fact` Tidecount: the water returns a little under four hours after 08:18, sooner than both tide marks; the far channels by the customs house flood first.
- T4 `skill_check` You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 3  ·  Base success (DC): 9  ·  vs Philippa Kemp power 7 Result: failure (failure)  ·  margin -6 You fail. The moment offers nothing useful.
- T5 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T5 `system` Travel action with no MOVE op; server moved the player to the tally house (new_location).
- T5 `quest` New job offered: Raise the customs-house bell
- T5 `skill_check` You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 2  ·  Base success (DC): 8  ·  vs Philippa Kemp power 6 Result: failure (failure)  ·  margin -6 It does not work; you spend effort and get air.
- T6 `self_check` {"passed": true, "issues_found": ["Una Rendle calls the player Tarrow's girl; nothing says she has been told the player's name."], "corrections_made": ["Verifier replaced narration.", "Verifier replaced turn_summary.", "Deterministic entity name/code repair applied to narration."], "reference_check"
- T7 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T7 `quest` Quest accepted: Raise the customs-house bell
- T7 `quest` Tam Kemp signed for the customs-house bell yesterday and has not come back; his name is not crossed out.
- T7 `skill_check` You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 19  ·  Base success (DC): 11  ·  vs Una Rendle power 9 Result: success (success)  ·  margin +8 It works as intended.
- T8 `venue_redirect` Philippa Kemp's General Store is entered from Saltmarrow; the journey ends there.
- T8 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T8 `skill_check` You rolled 14 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 14  ·  Base success (DC): 11  ·  vs Una Rendle power 9 Result: success (success)  ·  margin +3 It works as intended.
- T9 `inventory_reject` Rejected unearned gain: tarred rope x1 (named=True, prose_says_arrived=False, prose_outcome=loss, owned=False)
- T9 `self_check` {"passed": true, "issues_found": ["Narration calls the three coins the last of the week's copper; the player holds 12 gold and keeps 9."], "corrections_made": ["Verifier replaced narration.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: 
- T9 `dice` gold (trivial): 1d4 [2] = 2, lost (-2) · item_count (small): 1 +1 = 1 · gold loss voided (-2): nothing was bought; tarred rope did not change hands
- T9 `skill_check` You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 7  ·  Base success (DC): 12  ·  vs Philippa Kemp power 10 Result: failure (failure)  ·  margin -5 You fail. The moment offers nothing useful.
- T10 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T10 `dice` item_count (small): 1 +1 = 1
- T10 `skill_check` You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 9  ·  Base success (DC): 7  ·  vs Philippa Kemp power 5 Result: success (barely)  ·  margin +2 You just barely scrape through.
- T11 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T11 `fact` At 09:00 the water in the deep channel was cold and flowing slightly outward, toward the absent sea.
- T11 `skill_check` You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 5  ·  Base success (DC): 7  ·  vs Philippa Kemp power 5 Result: partial (partial)  ·  margin -2 A fragment of the truth, a half-open door, a costly glimpse.
- T12 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T12 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T12 `quest` A hand cart crossed the deep channel after the last water and turned toward the lower district, not the customs house; a small worn boot print beside the ruts.
- T12 `skill_check` You rolled 18 with your base of 10 (wisdom) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 18  ·  Base success (DC): 10 Result: success (success)  ·  margin +8 You succeed cleanly.
- T13 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T13 `system` Followed the cart ruts with no place named; the player stayed in The Deep Channel.
- T13 `fact` The cart ruts leave the deep channel by a low broken stretch of the right bank, a few yards past the steep part.
- T13 `skill_check` You rolled 2 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 2  ·  Base success (DC): 10 Result: failure (unskilled mishap)  ·  margin -8 Without training, the weapon/tool does as much harm to you as to the world. You are unskilled at wielding this — you
- T13 `injury` {"kind": "self_injury", "limb": "arm", "severity": false, "lasting": false, "health_delta": -1, "summary": "Botched Athletics: you hurt your arm.", "combat_penalty": {}}
- T13 `weather` Weather shifts to Cloudy.
- T14 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T14 `system` Followed the ruts with no place named; the player stayed in The Deep Channel.
- T14 `fact` The cart's exit ramp from the deep channel is soft under the crust; a small spread handprint in one rut shows someone else fell there too.
- T14 `skill_check` You rolled 1 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 1  ·  Base success (DC): 13 Result: critical failure (critical failure)  ·  margin -12 A brutal miss — something breaks, bleeds, or betrays you. You are unskilled at wielding this — you end up 
- T14 `injury` {"kind": "self_injury", "limb": "leg", "severity": true, "lasting": true, "health_delta": -6, "summary": "Botched Athletics: you hurt your leg.", "combat_penalty": {"mobility": -2, "attack": -1, "defense": -1}}
- T15 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draf
- T15 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T15 `skill_check` You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 7  ·  Base success (DC): 12 Result: failure (failure)  ·  margin -5 It does not work; you spend effort and get air.
- T16 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draf
- T16 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T16 `fact` There is a low hard stretch of bank on the outside of the deep channel's bend, a hundred paces past the cart ramp.
- T16 `skill_check` You rolled 3 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 3  ·  Base success (DC): 13 Result: failure (unskilled mishap)  ·  margin -10 You are unskilled at wielding this; the tool punishes the hand that holds it wrong. You are unskilled at wielding t
- T16 `injury` {"kind": "self_injury", "limb": "side", "severity": false, "lasting": false, "health_delta": -1, "summary": "Botched Athletics: you hurt your side.", "combat_penalty": {}}
- T17 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T17 `fact` Tidecount at 09:45: the water returns in a little over two hours; the deep channel is a return cut and will fill fast once the far channels are full.
- T18 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T19 `self_check` {"passed": true, "issues_found": ["relationships targets the player, who has no entity code."], "corrections_made": ["Verifier replaced relationships.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: revise; patched relationships.", "consi
- T19 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T19 `dice` xp (small): 1d6+2 [6] +2 = 8
- T19 `skill_check` You rolled 20 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 20  ·  Base success (DC): 11  ·  vs Jocosa Kettle power 9 Result: critical success (critical success)  ·  margin +9 You make it look effortless — clean, complete, and then some.
- T20 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T20 `system` Followed Tam first with no place named; the player stayed in The Deep Channel.
- T20 `skill_check` You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 19  ·  Base success (DC): 10  ·  vs Jocosa Kettle power 8 Result: success (success)  ·  margin +9 It works as intended.
- T21 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T21 `skill_check` You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 2  ·  Base success (DC): 11  ·  vs Jocosa Kettle power 9 Result: failure (bad nothing)  ·  margin -9 Wasted motion. The world does not even bother to answer.
- T22 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T22 `fact` The Lantern Wives' lamp between the two roofs was hung for Mara Tarrow, Isk's mother, last seen going into the rows there six years ago on a night the water came back early.
- T22 `skill_check` You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 13  ·  Base success (DC): 9  ·  vs Jocosa Kettle power 7 Result: success (success)  ·  margin +4 It works as intended.
- T23 `fact` Title earned: Wanderer — One who has walked many roads and seen many lands.
- T23 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draf
- T23 `skill_check` You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 13  ·  Base success (DC): 12  ·  vs Jocosa Kettle power 10 Result: success (barely)  ·  margin +1 You just barely scrape through.
- T24 `self_check` {"passed": true, "issues_found": ["relationships has Jocosa knowing Philippa Kemp; nothing in world_state links them."], "corrections_made": ["Verifier replaced relationships.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: revise; patche
- T24 `skill_check` You rolled 1 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 1  ·  Base success (DC): 14  ·  vs Jocosa Kettle power 12 Result: critical failure (critical failure)  ·  margin -13 Disaster. The attempt turns against you. Botched Persuasion / Speech: you sa
- T24 `blunder` Botched Persuasion / Speech: you say the one thing they did not want to hear.
- T24 `weather` The cloudy breaks; sky eases toward clear.
- T25 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T26 `self_check` {"passed": true, "issues_found": ["world_state has NPC G as Reinald, apprentice, but every earlier scene, the ledger and Philippa name the boy Tam Kemp, a carter; the record is wrong, not the prose."], "corrections_made": ["Verifier replaced npcs.", "Deterministic entity name/code repair applied to 
- T26 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T26 `skill_check` You rolled 10 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 10  ·  Base success (DC): 13  ·  vs Reinald power 11 Result: partial (partial)  ·  margin -3 You get something, but not everything you wanted.
- T27 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T27 `dice` xp (small): 1d6+2 [1] +2 = 3
- T27 `skill_check` You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 18  ·  Base success (DC): 8  ·  vs Reinald power 6 Result: success (success)  ·  margin +10 It works as intended.
- T27 `weather` Weather shifts to Light heat.
- T28 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draf
- T28 `skill_check` You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 7  ·  Base success (DC): 10  ·  vs Reinald power 8 Result: partial (partial)  ·  margin -3 A fragment of the truth, a half-open door, a costly glimpse.
- T29 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T29 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T29 `fact` Four doors past the old fish market, a drowned house's collapsed front wall makes a rubble ramp up to a low tiled roof with a broad chimney stack.
- T29 `skill_check` You rolled 20 with your base of 10 (intelligence) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 20  ·  Base success (DC): 13  ·  vs Reinald power 8 Result: critical success (critical success)  ·  margin +7 You make it look effortless — clean, complete, and then some.
- T30 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T30 `skill_check` You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 3  ·  Base success (DC): 10  ·  vs Reinald power 8 Result: failure (bad nothing)  ·  margin -7 You do so poorly it is almost as if you had done nothing at all.
- T31 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T31 `weather` The light heat breaks; sky eases toward clear.
- T32 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 1.0 after deterministic checks.", "Dropped 1 line(s) of speech the narration gave the player that the pla
- T32 `skill_check` You rolled 10 with your base of 10 (strength) and a modifier of -2 (attr +0 + skill +0 (untrained) + untrained -2). Total: 8  ·  Base success (DC): 13 Result: failure (failure)  ·  margin -5 It does not work; you spend effort and get air.
- T33 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T33 `dice` damage (trivial): 1 +1 = 1, lost (-1)
- T34 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 1.0 after deterministic checks."], "reference_check": "Deterministic verification policy cleared entity r
- T34 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T34 `skill_check` You rolled 8 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 8  ·  Base success (DC): 14 Result: failure (failure)  ·  margin -6 You fail. The moment offers nothing useful.
- T35 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T35 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T35 `skill_check` You rolled 1 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 1  ·  Base success (DC): 12 Result: critical failure (critical failure)  ·  margin -11 Disaster. The attempt turns against you. You are unskilled at wielding this — you end up taking your own s
- T35 `injury` {"kind": "self_injury", "limb": "side", "severity": true, "lasting": true, "health_delta": -2, "summary": "Botched Athletics: you hurt your side.", "combat_penalty": {"mobility": 0, "attack": -1, "defense": -1}}
- T35 `weather` Weather shifts to Steady storm.
- T36 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T37 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 0.97 after deterministic checks."], "reference_check": "Deterministic verification policy cleared entity 
- T37 `skill_check` You rolled 8 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 8  ·  Base success (DC): 9  ·  vs Jocosa Kettle power 7 Result: partial (partial)  ·  margin -1 You get something, but not everything you wanted.
- T38 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T38 `skill_check` You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 9  ·  Base success (DC): 9  ·  vs Jocosa Kettle power 7 Result: success (barely)  ·  margin +0 You just barely scrape through.
- T39 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 2 line(s) of speech the narration gave the player that the player did not say."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted
- T39 `quest` Step done: Raise the customs-house bell (Sign for the contract)
- T39 `dice` xp (small): 1d6+2 [3] +2 = 5
- T39 `skill_check` You rolled 12 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 12  ·  Base success (DC): 12  ·  vs Jocosa Kettle power 10 Result: success (barely)  ·  margin +0 It almost fails — then holds at the last breath.
- T40 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T40 `skill_check` You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 2  ·  Base success (DC): 12  ·  vs Jocosa Kettle power 10 Result: failure (bad nothing)  ·  margin -10 You do so poorly it is almost as if you had done nothing at all.
- T41 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T41 `skill_check` You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 15  ·  Base success (DC): 14  ·  vs Jocosa Kettle power 12 Result: success (barely)  ·  margin +1 You just barely scrape through.
- T42 `wait` Slept 120 minute(s). frontier dark fantasy · Day 1 · 12:45 → frontier dark fantasy · Day 1 · 14:45. Events: 0.
- T42 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 1.0 after deterministic checks."], "reference_check": "Deterministic verification policy cleared entity r
- T42 `weather` The steady storm breaks; sky eases toward clear.
- T43 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T43 `fact` The customs tower's first-floor room is dry; fresh small and large footprints in the grit lead up the spiral stair.
- T43 `skill_check` You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 5  ·  Base success (DC): 10  ·  vs Jocosa Kettle power 8 Result: failure (failure)  ·  margin -5 It does not work; you spend effort and get air.
- T44 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T44 `system` Followed the footprints with no place named; the player stayed in The Customs Tower.
- T44 `fact` The customs tower's second floor holds a working brass tide machine and years of tide figures in Mara Tarrow's handwriting; someone has been living there recently.
- T45 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 1.0 after deterministic checks."], "reference_check": "Deterministic verification policy cleared entity r
- T45 `fact` Mara Tarrow's newest tide note is dated today: the sea crossed the outer bar three hours early; 'H.' said the reeve would move the mark and say nothing; she wrote that the bell must be rung, and she would ring it if he would not.
- T45 `skill_check` You rolled 4 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 4  ·  Base success (DC): 13  ·  vs Tam Kemp power 11 Result: failure (bad nothing)  ·  margin -9 You do so poorly it is almost as if you had done nothing at all.
- T46 `self_check` {"passed": true, "issues_found": ["npcs creates Mara Tarrow but the narration never names the woman; create her when the story names her."], "corrections_made": ["Verifier replaced npcs.", "Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: rev
- T46 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T46 `quest` Step done: Raise the customs-house bell (Reach the old customs house)
- T46 `skill_check` You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 11  ·  Base success (DC): 7  ·  vs Tam Kemp power 5 Result: success (success)  ·  margin +4 You succeed cleanly.
- T47 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration.", "Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draf
- T47 `dice` xp (moderate): 2d6+6 [4, 6] +6 = 16
- T47 `skill_check` You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 15  ·  Base success (DC): 9  ·  vs Tam Kemp power 7 Result: success (success)  ·  margin +6 It works as intended.
- T48 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T48 `skill_check` You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 5  ·  Base success (DC): 13  ·  vs Tam Kemp power 11 Result: failure (bad nothing)  ·  margin -8 Wasted motion. The world does not even bother to answer.
- T49 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T49 `fact` The reeve secretly paid Mara Tarrow to watch the sea from the customs tower; Hereward Jessop fetched her figures monthly. She warned that the sea was returning; the reeve never warned the town.
- T49 `skill_check` You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 9  ·  Base success (DC): 7  ·  vs Tam Kemp power 5 Result: success (barely)  ·  margin +2 You just barely scrape through.
- T50 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder", "Deterministic entity name/code repair applied to narration.", "Skipped model verifier at certainty 1.0 after deterministic checks."], "reference_check": "Deterministic verification policy cleared entity r
- T50 `skill_check` You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 13  ·  Base success (DC): 12  ·  vs Tam Kemp power 10 Result: success (barely)  ·  margin +1 It almost fails — then holds at the last breath.
- T51 `self_check` {"passed": true, "issues_found": [], "corrections_made": ["Deterministic entity name/code repair applied to narration."], "reference_check": "Model verifier verdict: pass.", "consistency_check": "Draft accepted as written."}
- T51 `system` Travel action with no MOVE op and no resolvable destination; player stayed put.
- T51 `skill_check` You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (untrained)). Total: 9  ·  Base success (DC): 10  ·  vs Tam Kemp power 8 Result: partial (partial)  ·  margin -1 A fragment of the truth, a half-open door, a costly glimpse.

## Row counts

| table | rows |
| --- | --- |
| abilities | 1 |
| aliases | 0 |
| content_pack_entries | 0 |
| content_packs | 0 |
| conversations | 16 |
| dice_rolls | 49 |
| entity_titles | 1 |
| equipment_slots | 13 |
| events | 6 |
| gm_events | 11 |
| gm_notes | 1 |
| inventory | 5 |
| inventory_capacity_modifiers | 0 |
| journal | 255 |
| karma_history | 0 |
| locations | 10 |
| model_logs | 120 |
| name_ledger | 11 |
| npc_agendas | 0 |
| npc_family_ties | 0 |
| npc_player_relationships | 1 |
| npc_private_feelings | 0 |
| npcs | 11 |
| pacing | 5 |
| party_members | 0 |
| player | 1 |
| player_aliases | 0 |
| player_name_history | 1 |
| player_proficiencies | 2 |
| player_skills | 2 |
| quest_clocks | 11 |
| quest_steps | 3 |
| quests | 1 |
| relationships | 2 |
| response_drafts | 0 |
| setting_templates | 26 |
| settings | 19 |
| sqlite_sequence | 25 |
| tile_image_run_disable | 0 |
| tile_images | 0 |
| tile_states | 38 |
| titles | 15 |
| town_cells | 0 |
| town_seen | 0 |
| turn_snapshots | 12 |
| turn_summaries | 51 |
| verification_memory | 207 |
| watched_npcs | 0 |
| world_facts | 5 |
| world_maps | 0 |
| world_presets | 8 |
| world_races | 1 |
