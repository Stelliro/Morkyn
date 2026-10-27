| Turn | Severity | Class | What happened | Evidence |
|---|---|---|---|---|
| T02 | S3 | drift | Bakery "Prowse and Daughters" (T01) became "Verity Halloway's Bakery"; pay changed from "a loaf" to "fifteen gold plus room and board" for a fortnight | turns/002.json |
| T02 | S2 | agency | "You ask if that includes food as well." narrator writes my question | turns/002.json |
| T02 | S1 | job | I accepted @Q1; no acceptance/pay recorded, quest not updated (delta only new place) | turns/002.json |
| T03 | S1 | money | Prose sets "fifteen gold pieces" on the counter, purse stays 12 and no job-paid state; also pay figure (15 gold = 150000 cu vs purse 12) is absurd | turns/003.json |
| T03 | S2 | agency | narrator writes my spoken line `"Yes," you say ... "I can start now."` | turns/003.json |
| T04 | S3 | reset | Verity greets me afresh ("Ah, good morning! ... What can I get for you today?") after hiring talk; my question about what to do first unanswered | turns/004.json |
| T04 | S1 | job | quest step "#2 Measured out the flour" filed, nothing in prose measured flour | turns/004.json |
| T05 | S1 | money/item | Prose: "Take the loaf" ... "She takes the six copper from you and gives back three in change." Save: purse unchanged (spend_voided), loaf refused (`refused loaf of baked goods`), inventory still 3 clothes. Stated 3-copper purchase and handed loaf not settled | turns/005.json (turn-66353f77-000006-player.json) |
| T05 | S1 | money | Prose sum (six copper taken) differs from my stated three copper | turns/005.json |
| T05 | S3 | echo | Narrator writes my offer as a quote: "Would you accept three copper for a loaf of... ah, this one looks fine." | turns/005.json |
| T00 | S1 | items | Starting inventory lacks Hesper's brass-bound grimoire | turns/000.json |
| T06 | S3 | engine text | Narration ends with "=== OPS FOCUS: sensory SCENE: action GOAL says, ... SUMMARY says, ..." leaked into prose | turns/006.json |
| T06 | S1 | place | I did not ask to leave; narrator walked me out to Thornhallow and the location moved (L2 -> L1) | turns/006.json |
| T06 | S3 | item name | loaf filed as "steaming hot baked good" | turns/006.json |
| T07 | S2 | agency/identity | Narrator makes "a young hedge-mage named Wren" a bakery assistant who speaks ("Four coppers? It's barely fit for pig slop") and sees me as "boy"; I speak/act as the player is replaced | turns/007.json |
| T07 | S1 | money/item | Sale stated: "Very well - four coppers for your efforts." Save: purse 11 unchanged, loaf still held | turns/007.json |
| T07 | S3 | drift | Verity relocated to a baker's cart in the square (still tagged [[A]]) | turns/007.json |
| T08 | S2 | agency | "Your mind wanders to the task ahead - finding the Chandlers' Guild hall and offering them the five silver pieces set aside for their debt." narrator writes my thoughts and decides coin set aside | turns/008.json |
| T08 | S3 | drift | Guild hall never found/created; no place filed; "Two travelers are already stirring" rows created in town instead | turns/008.json |
| T09 | S3 | drift | Travel by #L2 saved correctly but prose opens "You step out of Verity Halloway's Bakery [[L2]]" then "You arrive back at" it | turns/009.json |
| T09 | S1 | people | Travelers 3 and 4 filed as new rows while Travelers 1 and 2 (T08, at Thornhallow) exist; prose "another traveler has joined the first one" (no count match) | turns/009.json |
| T10 | S3 | drift | "The right branch leads to Verity Halloway's Bakery [[L2]]" on the King's Road fork in the hills | turns/010.json |
| T11 | S3 | drift | The Greywold [[L3]] (hills) described as "an inn nestled in the shadow of Thornhallow [[L1]] keep"; bakery "just down the hall"; weather "rain-slick cobblestones" | turns/011.json |
| T11 | S2 | agency | `"What brings a wanderer like you to these wild hills?" you ask` - I asked a different question than the one I wrote; narrator wrote "You are Wren" | turns/011.json |
| T11 | S1 | place/people | Traveler 5 filed although the person is Eadric (already row #6); new place "Outside Thornhallow" L4 filed from a walk to the hills | turns/011.json |
| T12 | S1 | items | Prose: "you turn up a few scraps: A cracked clay token... An iron key... A scroll case carved from bone"; inventory unchanged (still clothes + baked good), delta has only clock. Finds do not reach inventory | turns/012.json |
| T12 | S1 | place | Ruins never filed as a place; prose climbs to ruins and descends to "Outside Thornhallow", save stays L4 | turns/012.json |
| T12 | S3 | dice | Perception failure (4) yet prose gives three finds, and "Nothing leaps out at you" followed by finds (self-contradiction) | turns/012.json |
| T13 | S3 | drift | Prose climbs to "the ruined tower" and ends "descend back towards Thornhallow [[L1]]"; save location unchanged Outside Thornhallow; ruined tower vs ring of stones in T12 | turns/013.json |
| T14 | S1 | people | Two rows (Figure 1, Traveler 6) filed for one "unnamed traveler" (prose: single figure); Eadric the earlier hooded traveler not reused | turns/014.json |
| T14 | S3 | drift | Location now "The High Pastures" (L5) though prose says rocky gullies/cliffs; "Thornhallow's crumbling outer wall" | turns/014.json |
| T16 | S1 | place | Prose stays in the alcove at "the gully [[L6]]"; save moves current_location L6 -> L5 (High Pastures) | turns/016.json |
| T16 | S1 | health | Health 20->19 with no injury in prose (melee check failure 5, nothing hit me) | turns/016.json |
| T16 | S1 | items | "holding the dagger ready" but inventory has no dagger | turns/016.json |
| T16 | S3 | hour | "early dawn / first light" at world minute 580 (about 09:40); also "early dawn" earlier turns said mid-morning | turns/016.json |
| T17 | S1 | creature | "you strike at the hare... clip its leg"; no hare row filed, notes `attack_not_found` (people []), no engine result line, no health to check | turns/017.json |
| T18 | S1 | energy | Candlelight costs 2 energy (7->5), brief says 1 (turn also carries ambient drain) | turns/018.json |
| T18 | S3 | drift | Prose says I have been chasing "the creature ... since dawn" and a traveler hitching a horse is named Jocelin Redfern (row #11) after being "unnamed traveler"/Figure 1/Traveler 6 | turns/018.json |
| T20 | S1 | travel | `#L2` on a bakery report: prose is the bakery [[L2]], save moves me L5 -> L1 (Thornhallow), `attack_target_absent` says Verity is at L1. Code travel landed one place off (F210 class again; T9 worked) | turns/020.json |
| T20 | S3 | reset | Verity greets me as a stranger ("What brings you in today? Need to purchase one of my famous steamed buns?"), ignores job and report | turns/020.json |
| T05-T20 | S1 | job | Quest Q1 accepted T3 (active), step 1 "Measured out the flour" marked completed T4 with no basis; completion/pay never reached (not earned) | db/turn-020.md |

## Worked
- T06 stated payment: three copper paid, purse_units 120000 -> 119997 and loaf item granted (T05 same wording voided it, T06 settled).
- T09 travel by #L2 moved the save to L2.
- T10 travel to the hills filed The Greywold (L3) and moved me.
- T01-T03 job offer filed as quest row Dough Prep (on offer, accepted T3).
- T19 `!wait 60 wait` moved clock exactly 60 min, energy +3, prose hour (10:54) agreed.
- No purse move with no stated sum in 20 turns (money held; but sales and the T05 purchase did not settle).
- Failed: creature row for the hare (T17), ruin finds to inventory (T12), sale (T07).
