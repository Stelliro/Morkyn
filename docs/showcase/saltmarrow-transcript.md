# Saltmarrow: full 100-turn transcript

Every turn of the run, as shipped: the player's line, the narration the game kept, and what the engine recorded.
The model side (player and GM) was played by Claude through Mørkyn's cloud-API path; see [saltmarrow-100-turns.md](saltmarrow-100-turns.md).

## Turn 0 · Saltmarrow

**Opening scene**

> Morning in Saltmarrow smells of dried weed and lamp smoke. From the old harbour wall you can see what the sea left behind forty years ago: a grey plain of mud running out to the horizon, ribbed with channels, and the roofs of the lower district standing up out of it like teeth. Mooring rings hang on the wall above your head, rusted open, waiting for boats that stopped coming before you were born.
>
> A crowd of runners has already gathered at the guild's tally board, where a clerk in an ink-stained apron is nailing up the day's contracts. One sheet is pinned higher than the rest and carries the guild's red thumbprint: the bell of the old customs house, wanted whole, paid in coin rather than credit. Two runners read it, laugh, and walk away. The customs house sits furthest out on the flats.
>
> Below the board, Hereward Jessop, the reeve's tide clerk, a thin man with a slate and a satchel of chalk, is redrawing the tide marks on the wall. Yesterday's dry tide is still there, ghosted under his new line, and the two do not agree. He has moved the opening two hours earlier and keeps glancing at the sky as if it might argue.
>
> At the chandlery door behind you, a woman is hanging bundles of tallow candles from a pole. She is Philippa Kemp, and she sells lamp oil to every runner who goes out. Today she is not calling her prices. She is studying the faces coming off the stairs from the flats, one by one, and when yours comes level with her she steps into your way.
>
> "You run the flats," she says. "My nephew Tam went out at the last dry tide with a hand cart. Did you see a boy with a hand cart?"

<details><summary>Engine</summary>

- system: Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, do not seed default player skills beyond any recorded weak skill seed, and set any mode
- Verifier replaced narration.
- rumor: Philippa Kemp's nephew Tam went out on the flats at the last dry tide with a hand cart and has not come back.
- fact: The guild posted a coin-paid contract for the bell of the old customs house, furthest out on the flats.

</details>

*State after: health 20/20, energy 16, XP 0, gold 12.*

## Turn 1 · Saltmarrow

**Player:** "No boy with a cart, not on my stretch," I tell Philippa. "Which channel did Tam take, and when did he leave?"

> Philippa Kemp hears "no" and nothing after it. Her eyes have already left you for the stairs, where two more runners are coming up with mud to the knee and sacks over their shoulders.
>
> "Then you were looking at your own feet," she says, not unkindly, just tired. "Everyone who goes out says the same. Not my stretch. Not my channel." She ties off the last bundle of candles with a jerk that nearly snaps the string. "If I knew which channel he took, I'd not be standing here asking strangers."
>
> She steps past you to the next runner, a broad man with a split lip, and asks him the same question in the same words. He shakes his head before she has finished.
>
> Along the wall, Wulfstan the weaver has come out of his doorway to watch, a skein of grey wool looped over one arm. He catches your eye, glances at Philippa's back, and gives the smallest shrug, as if to say she has been at this since dawn. Then he goes back inside.
>
> Below the tally board, Hereward Jessop finishes his new chalk line and steps back to look at it. The two tide marks sit one above the other on the wall, two hours apart, and he does not rub out the old one.

<details><summary>Engine</summary>

- Verifier replaced relationships.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -8

</details>

*State after: health 20/20, energy 16, XP 0, gold 12.*

## Turn 2 · Saltmarrow

**Player:** I cross to the tide clerk at the wall. "Dry feet. Why'd you move the dry tide two hours early?"

> You cross the few yards of wet flagstone to the wall. Hereward Jessop hears the greeting and does not give the answer to it. He blows chalk dust off his slate, writes something small in the corner, and keeps his back to you as if the wall were the only thing on the harbour that could talk.
>
> The new mark is fresh and square. The old one under it is smudged where someone has already tried to rub it out with a thumb and given up.
>
> It is Wulfstan who answers, from his doorway two houses along. He has come back out with the grey skein and is winding it onto his fist as he talks.
>
> "He won't tell you," he says. "Asked him myself at first light. Reeve's orders, that's all he'll say, and he's said it to every runner on the wall." He tips his head toward the mud. "But I'll tell you what I saw from my window at dawn. The water was in the far channels already. Hours before it should have been. Then it went out again like it had forgotten something."
>
> He snaps the wool off short with his teeth.
>
> "Jessop chalked it after he came back from the reeve's house. Not before."

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +2

</details>

*State after: health 20/20, energy 16, XP 0, gold 12.*

## Turn 3 · Saltmarrow

**Player:** I flip open my mother's tide-reckoner, set it against the two chalk marks, and use Tidecount to feel for how long until the water comes back.

> The tide-reckoner opens with a click that is louder than it should be. Its brass face is scratched with channel names in your mother's small hand, and the needle settles, shivers, and settles again. You hold it up beside the chalk until both marks sit behind the glass.
>
> Then you stop looking and let Tidecount do the reading. It comes the way it always comes, as a slow pressure along the jaw, like biting down on something cold. The flats are empty now; you can feel that much as plainly as the stone under your boots. But the water is not far. It is sitting out past the furthest channels, close, and it is coming back in a little under four hours. Not at the old mark. Not at Jessop's new one either. Sooner than both.
>
> And it is not coming evenly. The far channels fill first, out where the customs house stands, then the water runs back toward the wall along the deep cuts. Anyone working the far district would have the least time of all.
>
> Hereward Jessop has turned around. He looks at the open reckoner in your hand the way people look at a fortune-teller's cards.
>
> "Put that away," he says. "The reeve's mark is the mark. If you want to go out on a guess, go out on a guess, but don't stand at my wall reading that old clock at people."

<details><summary>Engine</summary>

- Verifier replaced narration.
- fact: Tidecount: the water returns a little under four hours after 08:18, sooner than both tide marks; the far channels by the customs house flood first.
- check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

</details>

*State after: health 20/20, energy 15, XP 0, gold 12.*

## Turn 4 · The Tally House

**Player:** I go to the tally board and ask the guild clerk what the customs-house bell pays, and whether I can sign for it.

> You walk the length of the wall to the tally board. The guild clerk in the ink-stained apron is gone; the shutter of the tally house beside the board is half down, and a hand bell sits on the sill for anyone who wants to wake whoever is inside.
>
> The customs-house sheet is still pinned high, above the rest. Up close you can read it: one bronze bell, the old harbour bell from the customs house tower, to be brought to the tally house whole and uncracked. Thirty coin on delivery. Under the sum, in a different ink, someone has added: no advance, no credit, no claims for lost carts.
>
> Hereward Jessop has followed you along the wall with his chalk satchel, on his way somewhere else. He stops long enough to tap the sheet with his slate.
>
> "You sign at the window," he says. "Ring and wait. They'll put your name in the book and your name on the bell, and if you come back without it, your name stays in the book." He looks at the far flats, then at you. "Thirty coin is what they pay when nobody local will go. Philippa Kemp Ask yourself why the out-of-towners laughed."
>
> He walks on toward the reeve's end of the harbour without waiting for an answer.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op; server moved the player to the tally house (new_location).
- quest: New job offered: Raise the customs-house bell
- check: You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

</details>

*State after: health 20/20, energy 14, XP 0, gold 12.*

## Turn 5 · The Tally House

**Player:** I ring the hand bell on the sill and wait at the window to sign for the bell.

> The hand bell is cracked, and it makes a flat clank instead of a ring. You give it two, and then you wait.
>
> Inside the tally house something scrapes across a floor. The shutter goes up the rest of the way with a bang, and a woman leans her elbows on the sill: the clerk from the board, ink still on her apron, now with a pen behind each ear. Close up she is older than she looked at a distance, grey at the temples, with the flat patience of someone who has watched a lot of runners go out.
>
> She follows your eyes to the high sheet on the board and does not need telling which contract.
>
> "The customs bell," she says. She pulls a long ledger out from under the counter and lets it fall open on the sill. Most of the page is names with lines through them. "Una Rendle. I keep the book. Name goes here, mark goes here. The bell comes back whole or it doesn't come back. Lose a cart, lose a rope, that's your loss, not the guild's."
>
> She uncaps the ink, turns the ledger to face you, and holds out the pen.

<details><summary>Engine</summary>

- Verifier replaced narration.
- Verifier replaced turn_summary.

</details>

*State after: health 20/20, energy 14, XP 0, gold 12.*

## Turn 6 · The Tally House

**Player:** I take the pen and write my name in the book: Isk Tarrow. "Has anyone else signed for the customs bell before me?"

> The pen is cheap and scratchy, and the ink is thinned with something that smells of vinegar. You write your name under the last line, Isk Tarrow, and the letters sit wet and dark at the bottom of a page full of crossings-out.
>
> Una Rendle turns the ledger back toward herself, reads your name, and blots it with the side of her hand.
>
> "Before you?" She runs a finger up the page without looking at it. She knows where it goes. "Two this month. A pair of brothers off the coast road, signed together. One came back without the bell and without his brother." The finger stops on a double line. "Crossed out the both of them."
>
> She turns back one page.
>
> "And yesterday a boy put his name down for it. Tam Kemp. Wrote it big, like he was proud of it." She taps a name that has no line through it. "Not crossed out. Book says he's still out there, and the book only knows what people come back and tell it."
>
> She closes the ledger on your wet name and looks at you over it.
>
> "Dry tide's on the reeve's mark. Bell's in the tower, if the tower's still standing. Bring it back whole."

<details><summary>Engine</summary>

- quest: Quest accepted: Raise the customs-house bell
- quest: Tam Kemp signed for the customs-house bell yesterday and has not come back; his name is not crossed out.
- check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +8

</details>

*State after: health 20/20, energy 14, XP 0, gold 12.*

## Turn 7 · Saltmarrow

**Player:** I go back along the wall into Philippa's chandlery. "Tam signed for the customs bell yesterday. That's where he went." Then I ask her for a coil of rope and what it costs.

> You leave the tally window and walk back along the wall, past Wulfstan's shut door, to the chandlery. Over its lintel someone has painted Philippa Kemp's General Store, but nobody on the wall has ever called it anything but the chandlery. Inside it is dim and close, hung with candles, coiled line, tins of pitch and lamp wicks bundled like straw. Philippa Kemp is behind the counter, cutting wick with a knife too big for the job.
>
> She looks up when you come in, already shaking her head, ready to hear another no.
>
> Then she hears what you actually said. The knife stops. For a moment she just looks at you, and her face does something complicated, relief and fright arriving at the same time and neither one winning.
>
> "That stupid boy. That stupid, stupid boy." She puts the knife down very carefully, as if she does not trust her hands with it. "He said he'd find a job that paid in coin. I thought he meant carting for the guild." She wipes her face with the back of her wrist. "The customs house. Nobody goes that far out."
>
> You ask about the rope, and she reaches up without looking and pulls down a coil of tarred hemp, thirty feet, and drops it on the counter between you.
>
> "Four coin, on any other day." She keeps her hand on it. "Three for you, if you're going out where he went. And if you see him, you tell him his aunt will skin him."

<details><summary>Engine</summary>

- venue_redirect: Philippa Kemp's General Store is entered from Saltmarrow; the journey ends there.
- check: You rolled 14 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +3

</details>

*State after: health 20/20, energy 14, XP 0, gold 12.*

## Turn 8 · Saltmarrow

**Player:** I put three coin on the counter for the rope. "I'll tell him. Then I'll bring him back so you can do it yourself."

> You count three coins out of your purse and set them on the counter, one at a time, beside the rope. They are old copper, green at the edges.
>
> Philippa Kemp sweeps them into her palm without counting them again and slides the coil across to you. The tar on it is fresh enough to come off on your fingers.
>
> It is the promise she does not take.
>
> "Don't," she says. She says it flatly, to the counter, not to you. "Don't tell me you'll bring him back. Every runner who's ever stood there has told some mother or sister or aunt the same thing, and half of them are names in Una's book with a line through them." She drops the coins into a tin under the counter, and the lid goes on hard. "Find the bell. If you find him, you find him. I'll not hang my hopes on a stranger's mouth twice in one week."
>
> She picks up the knife again and goes back to cutting wick, very neatly, as if the conversation has already happened and she has decided how it ended.
>
> Out on the wall, the morning crowd is thinning. The runners who are going out have gone down the stairs to the flats.

<details><summary>Engine</summary>

- inventory_reject: Rejected unearned gain: tarred rope x1 (named=True, prose_says_arrived=False, prose_outcome=loss, owned=False)
- Verifier replaced narration.
- dice: gold (trivial): 1d4 [2] = 2, lost (-2) · item_count (small): 1 +1 = 1 · gold loss voided (-2): nothing was bought; tarred rope did not change hands
- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -5
- dice: player.gold_delta band trivial -> -2
- dice: item:tarred rope band small -> 1

</details>

*State after: health 20/20, energy 14, XP 0, gold 12.*

## Turn 9 · Philippa Kemp's General Store

**Player:** I check my pack: no rope. "Philippa, I'll buy that coil of tarred rope for three coin."

> You go through your pack where you stand inside the chandlery door, and the rope is not in it. Philippa Kemp watches you search with the expression of someone who has sold a great deal of rope to a great many people in a hurry.
>
> "Three coin," she says, and lifts the coil of tarred hemp back onto the counter from wherever it had gone. "Same as I said."
>
> You count three coins into her palm. She closes her hand on them, drops them into the tin under the counter, and pushes the coil across until it is against your chest.
>
> "Over the shoulder, not in the pack," she says. "In the pack it's no use to you when you're up to your waist." She shows you with her own hands, a loop and a twist, so it sits across the body and comes free with one pull. It is the first thing she has done all morning that is not about Tam, and she does it quickly, like a habit she is glad of.
>
> Through the open door the light on the wall has gone harder and whiter. Down on the flats the first runners are small figures already, picking their way out along the ribs of the channels.

<details><summary>Engine</summary>

- dice: item_count (small): 1 +1 = 1
- check: You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: success (barely)  ·  margin +2
- dice: item:tarred rope band small -> 1

</details>

*State after: health 20/20, energy 14, XP 0, gold 9.*

## Turn 10 · The Deep Channel

**Player:** I step back out onto the wall, go down the stairs onto the flats, and head out along the deep channel toward the customs house.

> Philippa Kemp does not look up from her wick as you go. The bell over the chandlery door knocks once behind you.
>
> The stairs down from the harbour wall are cut stone, worn into dips by forty years of boots, and they end not in water but in a shelf of packed grey mud scattered with broken shell. You step off the last one and the ground gives a little, the way it always does, and then holds.
>
> The deep channel starts right below the wall: a long trench in the mud where the old harbour mouth used to run, wide enough to have floated ships and now floored with a skin of standing water that does not reach your ankles. Runners use it because its bottom is firm. You go down the slope into it and start walking out.
>
> The town shrinks behind you faster than seems fair. Ahead, the drowned roofs of the lower district stand up out of the flats in rows, black against the white sky, and far beyond them, alone, is a square tower with its top broken off. The customs house. It looks close. It always looks close.
>
> The water in the channel bottom is colder than it should be for the hour, and when you look down it is moving, very slightly, the wrong way. Outward. Toward the sea that is not there.

<details><summary>Engine</summary>

- fact: At 09:00 the water in the deep channel was cold and flowing slightly outward, toward the absent sea.
- check: You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -2

</details>

*State after: health 20/20, energy 14, XP 0, gold 9.*

## Turn 11 · The Deep Channel

**Player:** I keep walking out along the channel and watch the mud on both banks for hand-cart wheel tracks.

> You walk slowly enough to read the banks. The mud on either side of the channel is a record of everything that crossed it since the last water: bird feet, the long smears where runners slid down, the deep twin holes of someone who stood still too long and had to pull out.
>
> Most of it is boots. Then, a quarter of a mile out, you find what you were looking for. Two narrow wheel ruts, a hand's width apart, come down the left bank at a slant, cross the channel floor, and climb out again on the right. The edges are still sharp. Whoever pushed that cart came through after the last water went out, not before.
>
> They do not go on toward the customs house. On the right bank the ruts turn away from the tower and run straight for the drowned rows of the lower district, between two roofs that stand up out of the mud like a gate.
>
> Beside the ruts, pressed deep where the cart must have bogged, is a single boot print, small, the heel worn down on the outside. A boy's foot, or a short man's. Then nothing for a stretch, as if the cart was hauled out by main force, and the ruts go on.
>
> Behind you, back toward the wall, the channel water has stopped moving outward. It lies quite still now, and very clear.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- quest: A hand cart crossed the deep channel after the last water and turned toward the lower district, not the customs house; a small worn boot print beside the ruts.
- check: You rolled 18 with your base of 10 (wisdom) and a modifier of +0 (attr +0 + skill +0 (untr | Result: success (success)  ·  margin +8

</details>

*State after: health 20/20, energy 14, XP 0, gold 9.*

## Turn 12 · The Deep Channel

**Player:** I climb out of the channel and follow the cart ruts toward the two roofs, keeping one eye on the tower.

> The right bank is steeper than it looked from the channel floor. You get a boot into the slope where the cart ruts climb out, reach for the lip with your left hand, and pull.
>
> The lip comes away. A slab of sun-crusted mud the size of a door peels off the bank under your weight and drops, and you go with it, sliding back down the slope in a spray of grey slurry. You throw out your right arm to stop yourself and it takes the whole of your weight at the wrong angle. Something in the elbow gives a hot, sick twinge that runs all the way up into your shoulder.
>
> You end up sitting in the channel floor in ankle-deep water with the rope coil twisted round under you and the slab of bank in pieces at your feet. The arm still works. It does not want to.
>
> The cart ruts climb out three yards further along, where the bank is lower and broken down by the cart's own wheels. Tam, if it was Tam, found the easy way up. You can see it plainly now, from down here.
>
> Out past the drowned roofs the customs tower stands where it stood, and the water in the channel bottom lies still and clear around your boots.

<details><summary>Engine</summary>

- system: Followed the cart ruts with no place named; the player stayed in The Deep Channel.
- fact: The cart ruts leave the deep channel by a low broken stretch of the right bank, a few yards past the steep part.
- check: You rolled 2 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (unskilled mishap)  ·  margin -8
- injury: {"kind": "self_injury", "limb": "arm", "severity": false, "lasting": false, "health_delta": -1, "summary": "Botched Athletics: you hurt your arm.", "combat_penalty": {}}

</details>

*State after: health 19/20, energy 13, XP 0, gold 9.*

## Turn 13 · The Deep Channel

**Player:** I get up, climb out where the cart wheels broke the bank down, and follow the ruts toward the two roofs.

> You get your feet under you and wade the few yards along the channel floor to where the cart came out. Here the bank is broken down into a ramp of churned mud, scored with the two ruts and the scuffs of whoever pushed. It looks like the easiest climb on the whole channel.
>
> It is also the wettest. The cart's wheels have dug through the dry crust into the soft grey underneath, and the soft grey has been waiting all morning for a foot. You put your weight on the ramp, take two steps up it, and on the third your left leg goes into the mud to the knee as if there were nothing under it at all.
>
> You pitch forward. Your knee stays where it is. For one long moment the whole of you is moving and that one leg is not, and then something on the outside of the knee gives with a pop you feel more than hear. You land on your bad elbow for good measure.
>
> When you have got your breath back you are lying on the ramp with your face a hand's width from one of the cart ruts, and your leg is still in the hole. It comes out slowly, with a sucking noise and a lot of pain, and it holds your weight when you test it, just. You are still below the lip of the bank.
>
> From down here you can see something in the rut by your face: a long scrape in the mud, and pressed into it, the print of a hand. Small. Fingers spread. Someone else fell here too.

<details><summary>Engine</summary>

- weather: Weather shifts to Cloudy.
- system: Followed the ruts with no place named; the player stayed in The Deep Channel.
- fact: The cart's exit ramp from the deep channel is soft under the crust; a small spread handprint in one rut shows someone else fell there too.
- check: You rolled 1 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: critical failure (critical failure)  ·  margin -12
- injury: {"kind": "self_injury", "limb": "leg", "severity": true, "lasting": true, "health_delta": -6, "summary": "Botched Athletics: you hurt your leg.", "combat_penalty": {"mobility": -2, "attack": -1, "defense": -1}}

</details>

*State after: health 13/20, energy 10, XP 0, gold 9.*

## Turn 14 · The Deep Channel

**Player:** I go slow this time: I lie flat and crawl up the ramp on my belly to spread my weight, testing each handhold before I trust it.

> The sky has gone over while you lay in the mud. A flat grey lid of cloud has slid in from the landward side, and the light on the flats has turned the colour of pewter.
>
> You lie down on the ramp, belly to the mud, and spread yourself out like a frog on a pond. It is slow and it is filthy and it works, for a while. Most of them hold. You get your chin level with the top of the bank, then your shoulders.
>
> The last handhold is a ridge of crust that looks as solid as the others and feels as solid when you test it. It is lying. The moment you commit to it, it shears off clean in your fist, and the whole careful structure of your weight goes with it. You slide back down the ramp on your front, not fast, not far, two body lengths of grey slurry, and come to rest with your face in the cart rut again.
>
> Nothing new hurts. The knee is no worse, which is the best thing you can say about it.
>
> Above you, the lip of the bank is still where it was. The coil of tarred rope is still across your body, under you, pressing its tar into your tunic.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -5

</details>

*State after: health 13/20, energy 10, XP 0, gold 9.*

## Turn 15 · The Deep Channel

**Player:** Forget the ramp. I limp along the channel floor until the bank is low and firm, then climb out there.

> You leave the ramp and the cart ruts behind and limp on along the channel floor, one hand on the bank to take weight off the knee. The water around your boots is still and clear and very cold. Every few yards you push at the bank with your palm. Soft. Soft. Soft.
>
> A hundred paces on, the channel bends, and on the outside of the bend the bank drops to waist height and turns pale and dry, packed hard by the sun. You thump it with the heel of your hand and it rings like a board.
>
> You get your forearms on top of it and swing your good leg up. It nearly works. The bad knee will not bend far enough to follow, and for a moment you are half over the edge, hung on your stomach, with both legs kicking at nothing.
>
> You stay there a while. The side hurts when you breathe deeply, so you breathe shallowly.
>
> Above the edge of the bank, a little way off across the flats, the two roofs that the cart ruts were making for stand up out of the mud. From down here you can see that there is a lamp hanging from a pole between them, unlit, swinging very slightly in a wind you cannot feel.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- fact: There is a low hard stretch of bank on the outside of the deep channel's bend, a hundred paces past the cart ramp.
- check: You rolled 3 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (unskilled mishap)  ·  margin -10
- injury: {"kind": "self_injury", "limb": "side", "severity": false, "lasting": false, "health_delta": -1, "summary": "Botched Athletics: you hurt your side.", "combat_penalty": {}}

</details>

*State after: health 12/20, energy 10, XP 0, gold 9.*

## Turn 16 · The Deep Channel

**Player:** I sit still in the water, breathe shallow, and use Tidecount. How long until it comes back?

> You stop fighting the bank and sit still in the cold water, and let Tidecount come.
>
> It comes up through your jaw the way it always does, the cold-tooth ache, but sharper sitting down here in the channel than it was standing on the wall. The water is closer than it was at the harbour. Not much over two hours now, and the far channels first, as before. That has not changed.
>
> What has changed is the deep channel itself. You feel it now the way you would feel a draught along the floor of a room: this trench is one of the cuts the water comes home by. When the far channels are full, it will run back along here toward the wall, fast and all at once, and the channel you are sitting in will be the first thing on this side of the flats to fill.
>
> The ache goes, and leaves the ordinary aches behind it: knee, elbow, the hook under your ribs. The clouds have thickened. The light on the water at your feet has gone dull, and the lamp between the two roofs is a small dark mark against grey.
>
> Somewhere off to your left, out of sight beyond the bank, someone is whistling. Two notes, high then low, over and over, the way runners call to each other across the mud.

<details><summary>Engine</summary>

- fact: Tidecount at 09:45: the water returns in a little over two hours; the deep channel is a return cut and will fill fast once the far channels are full.

</details>

*State after: health 12/20, energy 8, XP 0, gold 9.*

## Turn 17 · The Deep Channel

**Player:** I whistle the call back, high then low, then shout: "Down in the deep channel! I can't get up the bank!"

> Your whistle comes out thinner than you meant, but it carries. The two notes go out over the flats and hang there. For a moment nothing answers. Then the call comes back, closer, high then low, and after it a voice.
>
> "Keep shouting! I'll find the edge!"
>
> You shout. Boots squelch along the top of the bank, stop, come on again. A head appears over the lip a little way along: a woman of fifty or so, wind-browned, with a man's oilskin hat jammed down over grey hair and a salvage hook on a long ash pole across her shoulders. She looks down at you sitting in the water, then at the soft ramp behind you, then at the way you are holding your side.
>
> "You tried the cart ramp," she says. "Everybody tries the cart ramp." She kneels at the edge, carefully, testing it with her knee first. "Jocosa Kettle. I run the north rows. You're not hurt so bad you can't hold on, are you?"
>
> She swings the pole round and lowers it down the bank to you, hook end first, the iron crook of it hanging at the height of your good hand.
>
> "Grab the shaft above the hook, not the hook. I'll take the weight. You walk up."

*State after: health 12/20, energy 8, XP 0, gold 9.*

## Turn 18 · The Deep Channel

**Player:** I grab the shaft above the hook and walk myself up the bank while Jocosa takes the weight. "Isk Tarrow. Thank you."

> You take the ash shaft in your good hand above the iron, and Jocosa Kettle leans back against it like a woman hauling a boat. With her weight on the other end, the bank is just a slope. You walk up it in four ugly steps, the bad knee complaining at every one, and at the top she grabs your collar and pulls the last of you over the lip onto the hard mud.
>
> You lie there a moment on dry ground, the whole flat grey world spread out around you at last instead of above you.
>
> "" Jocosa repeats, and something in her face changes, a door opening. "Mara Tarrow's girl? You've got her jaw." She coils the pole back onto her shoulder. "I ran the rows with your mother for nine years. Best tide-reader I ever knew, and she never trusted that brass thing either."
>
> She looks you over, the elbow, the knee, the way you are holding your side, and clicks her tongue.
>
> "You're going for the customs bell. I can see the guild's mark on your hand from here." She nods out past the two roofs, to the broken tower. "There's a boy out there already. Kemp's boy, with a hand cart. I saw him go into the rows yesterday, past the Lantern Wives' lamp, and I told him what I'll tell you: the rows are no road to the customs house. They're a maze, and the water knows it better than you."

<details><summary>Engine</summary>

- Verifier replaced relationships.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- dice: xp (small): 1d6+2 [6] +2 = 8
- check: You rolled 20 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: critical success (critical success)  ·  margin +9
- dice: player.xp_delta band small -> 8

</details>

*State after: health 12/20, energy 8, XP 8, gold 9.*

## Turn 19 · The Deep Channel

**Player:** "I'm going after Tam first, then the bell. Will you walk the rows with me? You know them and I don't."

> Jocosa Kettle does not answer at once. She looks at the two roofs, and the lamp between them, and then at the sky, which has closed down grey from one edge of the flats to the other.
>
> "Tide's early," she says. It is not a question. "You felt it. Your mother always knew before the wall did."
>
> She shifts the hook-pole on her shoulder and squints at your knee.
>
> "I'll walk you to the lamp and through the first two rows, because that's where I'm going anyway and I'll not have Mara's girl drown in a ditch I could have pointed at." She holds up one finger, crooked from some old break. "Past the second row you're on your own. I've a sling of copper pipe waiting on a roof out there, and it won't wait for the water and neither will I."
>
> She looks at you a moment longer.
>
> "And you walk where I walk. Not beside. Behind. Where I put my feet."
>
> She turns toward the roofs without waiting to see if you will argue, and starts off across the hard mud at a pace meant for someone with two good knees, then shortens it without a word.

<details><summary>Engine</summary>

- system: Followed Tam first with no place named; the player stayed in The Deep Channel.
- check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +9

</details>

*State after: health 12/20, energy 7, XP 8, gold 9.*

## Turn 20 · The Deep Channel

**Player:** I go with Jocosa, behind her, putting my feet where she puts hers, out toward the lamp.

> You go after Jocosa Kettle, and you do what she said: not beside, behind. Her boots leave clean prints in the hard mud, and you put yours into them one after the other, bad knee and all. It is slower than walking and harder, and she does not slow down for it.
>
> Twice she stops dead without warning and you nearly walk into her back. The first time she points with the butt of the pole at a patch of mud that looks exactly like the rest and says, "Soft," and goes round it. The second time she does not explain at all.
>
> "You're breathing like a bellows," she says over her shoulder. "Every runner on the flats can hear where you are." It is the most she says. She has gone quiet and closed since the bank, as if she has already spent what she had to say to Mara's girl and is not minded to spend more.
>
> The two roofs grow as you come on. They are the tops of tall houses, slate gone green, chimneys still standing, and the lamp hangs between them from a pole wedged across two gable ends. Close up it is an old ship's lantern, its glass smoked black inside. Under it, someone has tied a strip of red cloth to the pole, faded nearly pink.
>
> Jocosa stops beneath it and looks up, and for a moment her face is not closed at all.

<details><summary>Engine</summary>

- check: You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -9

</details>

*State after: health 12/20, energy 6, XP 8, gold 9.*

## Turn 21 · The Deep Channel

**Player:** "What's the red cloth for?" I ask Jocosa, keeping my voice low.

> Jocosa Kettle does not look away from the lamp.
>
> "The Wives tie a red one where a runner was last seen," she says, as low as you asked. "White if they found the body. Red if they never did." She reaches up with the hook-pole and touches the faded cloth, very lightly, the way you might touch someone's sleeve. "They hang a lamp and light it on the long-ebb nights, so whoever's out there can find their way home."
>
> She lowers the pole.
>
> "Six years this one's been red. They put it up the week your mother didn't come back." Her voice does not change at all. "This is the last place anyone saw her. Me. I saw her. She went in between these two roofs with a sack and a line, and she waved, and the water came back early that night."
>
> The wind you could not feel in the channel moves the lamp on its rope, and the smoked glass turns a little, and turns back.

<details><summary>Engine</summary>

- fact: The Lantern Wives' lamp between the two roofs was hung for Mara Tarrow, Isk's mother, last seen going into the rows there six years ago on a night the water came back early.
- check: You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +4

</details>

*State after: health 12/20, energy 6, XP 8, gold 9.*

## Turn 22 · The First Row

**Player:** I follow Jocosa in between the two roofs, into the first row.

> Jocosa Kettle ducks under the lamp pole without touching it and goes in between the two roofs, and you follow her into the first row.
>
> It is a street. It is different from inside. The mud comes up to the first-floor windows here, and the houses lean toward each other across the gap like people trying to hear something, so the light comes down grey and narrow. Doorways stand half buried. A shop sign still hangs from one bracket, a carved fish gone soft and black.
>
> Jocosa stops at the first corner and plants the butt of her pole.
>
> "Second row's to the left," she says. "Your boy's cart went right." She points with her chin. The ruts you lost at the channel are here again in the softer street mud, bending right, deeper into the district. "Right's the old fish market. Floor's rotten. Stay off anything with boards."
>
> She looks at you, at your knee, and her mouth goes tight.
>
> "That's the first row. I said two."

<details><summary>Engine</summary>

- fact: Title earned: Wanderer — One who has walked many roads and seen many lands.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- check: You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +1

</details>

*State after: health 12/20, energy 5, XP 8, gold 9.*

## Turn 23 · The Old Fish Market

**Player:** "Go get your pipe before the water does. Thank you, Jocosa." Then I follow the ruts right toward the fish market, keeping off anything with boards.

> It is the wrong thing to say, and you hear it as it leaves you. Before the water does.
>
> Jocosa Kettle goes very still. For a moment she looks exactly the way she looked under the lamp, and then she does not; her face shuts like a box.
>
> "Don't you tell me about the water," she says. Quiet, and much worse for it. "I know what the water does. I stood at that lamp and watched it do it." She swings the pole off her shoulder and grips it in both hands, not at you, just to have hold of something. "Your mother used to talk like that. Easy. Like it was weather."
>
> She turns left toward the second row without another word, and the mud takes her footprints, and she does not look back.
>
> You go right. The cart ruts bend round the corner and run on down the drowned street, deep and plain in the soft mud, and you keep to the middle of it, away from the doorways and their sagging boards. The houses give way to a long low shape on the right: a covered market, its tiled roof humped like a whale's back, half its tiles gone. The ruts go straight in under the eaves, into the dark.
>
> Something inside it is dripping, slow and steady, in a place where nothing should be wet yet.

<details><summary>Engine</summary>

- Verifier replaced relationships.
- check: You rolled 1 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: critical failure (critical failure)  ·  margin -13
- blunder: Botched Persuasion / Speech: you say the one thing they did not want to hear.

</details>

*State after: health 12/20, energy 5, XP 8, gold 9.*

## Turn 24 · The Old Fish Market

**Player:** I stop under the eaves to let my eyes get used to the dark, then call in: "Tam? Tam Kemp? Your aunt sent me."

> The dark under the eaves thins slowly. A long hall comes out of it: stone counters in rows, iron hooks hanging from the beams, and a floor of planks laid over whatever was underneath, black and furred with old weed. The cart ruts run in across the mud at the door and stop where the planks begin.
>
> Halfway down the hall there is a hole in the floor. A ragged one, the shape of a cart turned on its side, with snapped boards pointing down into it.
>
> Your voice goes down the hall and comes back to you off the stone. Then, from the hole, small and cracked:
>
> "Here! I'm here, I'm down here!" A scrabbling, and a gasp. "Don't come on the boards. Don't, they go. They just go."
>
> A pale hand shows for a moment at the broken edge, catching at a plank end, and drops back.
>
> "I can't get my leg out. The cart's on it." The voice is very young and trying hard not to be. "There's water coming up. It wasn't there this morning. It's coming up out of the floor down here, it's cold, it's at my chest."
>
> The dripping you heard is not dripping. It is the steady trickle of water running down into the hole from somewhere under the planks, and the sound of it rising.

<details><summary>Engine</summary>

- weather: The cloudy breaks; sky eases toward clear.

</details>

*State after: health 12/20, energy 5, XP 8, gold 9.*

## Turn 25 · The Old Fish Market

**Player:** "Hold on, Tam." I tie the rope round the leg of the nearest stone counter, stretch out flat on the boards to spread my weight, and feed the free end down the hole to him.

> The counter leg is stone, square and thick as your thigh, and it does not move when you throw your weight on the knot. You stretch out flat on the planks the way you did on the ramp, belly down, arms wide. The boards under you creak and sag but hold.
>
> "Rope coming, Tam. Take it."
>
> Below you, the boy is not listening. He is talking, fast and high, about the cart and the water and how he only meant to cut through, how the floor just went, and his hands are slapping at the water instead of reaching up. The rope's end hangs a foot above his head and swings.
>
> You see him properly now: a thin face, white with cold, hair plastered flat, the water at his collarbones. The cart lies on its side across his legs, one wheel still turning slowly in the current, and the water around him is moving, sucking in under the stone footings from somewhere outside.
>
> He finally sees the rope and grabs it, two-handed, much too low, and pulls. The knot at the counter leg creaks. The board under your hip gives a short crack, like a knuckle, and the edge of the hole is a hand's width nearer your face than it was.
>
> "I've got it," he gasps. "I've got it. Now what?"

<details><summary>Engine</summary>

- Verifier replaced npcs.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 10 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: partial (partial)  ·  margin -3

</details>

*State after: health 12/20, energy 5, XP 8, gold 9.*

## Turn 26 · The Old Fish Market

**Player:** "Wrap it round under your arms, Tam, not in your hands. Then push on the cart with your free foot while I pull."

> Tam Kemp hears you this time. He gets the rope round his back and under his arms, fumbling at it with numb fingers, and knots it at his chest with a knot no runner would trust and you will not argue with.
>
> "Ready," he says. His teeth are going like a loom.
>
> You pull. Flat on your belly, you cannot pull with your back, so you pull with your arms and the good leg braced against a board seam, and the rope goes taut over the broken edge. Below, Tam plants his free foot against the cart's bed and shoves, and the cart rocks in the water. It does not lift. It rolls, a quarter turn, the far wheel coming up out of the water, and that is enough. You feel the rope jerk as the weight on it changes from a boy stuck to a boy coming.
>
> He comes up out of the hole in a rush of black water and splinters, gets one elbow over the edge, then the other, and you drag him by the rope across the boards until you are both lying flat on the planks a body length from the hole, breathing like bellows.
>
> His left leg drags. The trouser is torn open at the shin and the skin under it is already purple. But he is out.
>
> Behind you in the hole, the cart turns over the rest of the way with a sound like a slow sigh and goes under. The water in the hole is still rising. You can hear it.

<details><summary>Engine</summary>

- dice: xp (small): 1d6+2 [1] +2 = 3
- check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +10
- dice: player.xp_delta band small -> 3

</details>

*State after: health 12/20, energy 5, XP 11, gold 9.*

## Turn 27 · The Old Fish Market

**Player:** I untie the rope from the counter and coil it back over my shoulder, get Tam's arm across my neck, and we crawl back along the planks toward the door.

> The knot at the counter leg has pulled so tight on the wet rope that it takes you three tries and a broken nail. Then the coil is back over your shoulder, heavier for the water in it, and Tam Kemp is half on top of you with his arm round your neck and his breath sour and quick in your ear.
>
> You choose the boards; he follows where you put your hands. Twice a plank groans under the pair of you and you both stop dead and wait, and it holds.
>
> The door is a square of grey daylight, and then you are under the eaves with mud under your knees instead of rotten wood, and you can sit up.
>
> Tam does not sit up. He twists round and stares back into the dark of the hall, toward the hole and the sound of rising water.
>
> "The cart," he says. "It's my uncle's cart. It was his before he died. I can't go back to Aunt Philippa without the cart." He pulls at your sleeve, his face fierce and white. "There's a bell-rope down there too. Off the customs house, I found it in the rows, real bronze-work on the clapper end. If we could just get the cart up..."
>
> He is not listening to the water. He is fourteen, at most, and he is not listening to anything.

<details><summary>Engine</summary>

- weather: Weather shifts to Light heat.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -3

</details>

*State after: health 12/20, energy 5, XP 11, gold 9.*

## Turn 28 · The Old Fish Market

**Player:** "No cart's worth you, and your aunt would say the same. The water's coming back early, Tam, I can feel it. We get up high now." I look along the row for a roof we can climb onto.

> Tam Kemp opens his mouth to argue, and the word "aunt" stops it. He looks at the hole in the hall floor for a long moment. Then he wipes his nose on his wet sleeve and nods, once, without looking at you.
>
> "She'll kill me," he says. "About the cart."
>
> "Better than the water," you could say, but he has already turned to look where you are looking.
>
> The row runs on past the fish market, the drowned houses shouldering up out of the mud on both sides. Most of them are no use: steep slate, nothing to hold. But four doors down, on the far side, one house has lost its whole front wall to some old collapse, and the rubble has slumped out into the street in a long slope of stone and broken beams that reaches almost to the eaves. Above it, the roof is a low pitch of old tiles with a stone chimney stack standing up out of the ridge, broad enough for two people to put their backs against.
>
> It is the best thing you have seen all day. A ramp you can walk up, a roof that will stand clear of anything but the worst water, and a chimney to tie a rope to.
>
> The air has gone warm and close since you went into the market, the cloud burned off and a hazy heat pressing down on the flats. Somewhere out past the rows, a long way off, there is a sound you have not heard before in your life on the flats: a low, steady hiss, like a kettle a long way from boiling.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- fact: Four doors past the old fish market, a drowned house's collapsed front wall makes a rubble ramp up to a low tiled roof with a broad chimney stack.
- check: You rolled 20 with your base of 10 (intelligence) and a modifier of +0 (attr +0 + skill +0 | Result: critical success (critical success)  ·  margin +7

</details>

*State after: health 12/20, energy 3, XP 11, gold 9.*

## Turn 29 · The Chimney Roof

**Player:** I get Tam's arm over my shoulder again and we go four doors down to the rubble slope. I take him up it slowly, stone by stone, to the roof, and tie the rope round the chimney stack.

> Tam Kemp lets you take his weight, but he does not help. He hangs off your neck like wet washing and keeps looking back at the fish market door until the houses hide it.
>
> Four doors down, the rubble slope is better than it looked from the market: big stones bedded in hard mud, beams wedged among them like the rungs of a broken ladder. You go up it a stone at a time. You set your good foot, haul, set Tam's good foot, haul again. He makes no sound when his bad shin knocks a beam, which is worse than if he had cried out.
>
> The roof at the top is old red tile gone grey with salt, warm under your hands from the sudden heat. You get Tam onto it on his backside and let him slide down against the chimney stack, and he sits there with his knees up and his face turned away from you.
>
> The chimney is good stone, mortared, broad as a cart is long. You pass the rope twice round it and knot it, and it holds when you throw your weight back on it.
>
> From up here you can see the whole of the north rows laid out, roof after roof, and beyond them the open flats, and beyond those, where the sea used to be, a line. A long white line along the whole horizon, very thin, not moving that you can see. The hiss is louder up here.

<details><summary>Engine</summary>

- check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -7

</details>

*State after: health 12/20, energy 2, XP 11, gold 9.*

## Turn 30 · The Chimney Roof

**Player:** I sit down with my back to the chimney beside Tam, get my breath, and use Tidecount on that white line.

> The chimney stones are warm against your back. Tam Kemp is a hunched shape at your shoulder, still not speaking. You close your eyes and let Tidecount come, and for once it does not come gently.
>
> It hits like cold water in a bad tooth. The white line is the sea. Not the tide that comes back up the channels every night and goes out again, but the sea itself, the whole grey weight of it, standing up along the horizon where it has not stood in forty years. It is coming in over the outer flats the way water comes into a footprint: all at once and from every side.
>
> And it is coming early. You were right at the wall and right in the channel, but you were not right enough. Not an hour now. Less. The far channels are already full; the deep channel is filling; the rows will be next, and the water will not stop at the first-floor windows tonight.
>
> You open your eyes. Your mother's reckoner is in your hand without your remembering taking it out, and under the glass the needle is spinning, slowly and steadily, round and round, the way it never has.
>
> Beside you Tam has gone very still. He is looking at the line too.
>
> "That's not the tide," he says. "Is it."

*State after: health 12/20, energy 0, XP 11, gold 9.*

## Turn 31 · The Chimney Roof

**Player:** "No. It's the sea." I tie the rope's free end round Tam's waist, then round mine, so we're both fast to the chimney.

> "It's the sea," you tell him, and he does not argue.
>
> It is heavier than it should be; it has drunk half the fish market's water, and the tar has gone slick. You get it round Tam Kemp under his arms, over the old knot he made in the hole, and tie it off. That part goes well.
>
> Two turns round a chimney broad as a cart is long eat more line than you thought, and what is left after Tam is an arm's length of wet hemp with a frayed end. You try it round your waist and it will not meet. You try it round one thigh and the knot pulls loose as soon as you lean on it, the slick tar letting it slide.
>
> In the end you have a loop of it wound twice round your right fist, and the chimney at your back, and that is all.
>
> Tam sees. He starts to fumble at his own knot.
>
> It is not a hiss any more. It is a long low roar, very far off and getting less far, and under your hands the warm tiles of the roof have begun, very faintly, to hum.

<details><summary>Engine</summary>

- weather: The light heat breaks; sky eases toward clear.
- Dropped 1 line(s) of speech the narration gave the player that the player did not say.
- Dropped 2 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- check: You rolled 10 with your base of 10 (strength) and a modifier of -2 (attr +0 + skill +0 (un | Result: failure (failure)  ·  margin -5

</details>

*State after: health 12/20, energy 0, XP 11, gold 9.*

## Turn 32 · The Chimney Roof

**Player:** I wind the rope loop tighter round my fist, hook my other arm round the chimney stack, and hold on.

> You wind the loop until the wet hemp bites into the back of your hand, hook your other arm round the chimney stack, and hold.
>
> It comes down the rows like a cart down a hill. First the roar, then a wind that smells of salt and weed and something older, a cold, green, deep smell that has not been on the flats in forty years. Then the water itself: a brown wall no higher than a man, shoving a scum of foam and timber ahead of it, pouring into the street below you between the drowned houses and climbing them as if they were steps.
>
> It reaches the first-floor windows in the time it takes to breathe twice. It reaches the rubble slope you climbed and swallows it. Spray comes over the gutter and across the tiles, and for a moment the whole roof is white and you cannot see Tam Kemp at all, only feel the rope jerk taut in your fist.
>
> Then the wall has gone past, roaring on toward Saltmarrow, and what it leaves behind is water. Just water, brown and heaving, a hand's width below the roof's edge, slapping at the tiles. The rows are gone. There are only roofs now, standing up out of a moving sea like stepping stones, and chimneys, and here and there a lamp pole.
>
> Tam is still there, coughing, roped to the stone. The skin on the back of your hand is torn where the rope bit. You are both soaked to the bone, and the water is still rising, very slowly, toward the ridge.

<details><summary>Engine</summary>

- dice: damage (trivial): 1 +1 = 1, lost (-1)
- dice: player.health_delta band trivial -> -1

</details>

*State after: health 11/20, energy 0, XP 11, gold 9.*

## Turn 33 · The Chimney Roof

**Player:** We wait it out on the roof. I keep hold of the chimney and the rope and watch how fast the water climbs the tiles.

> You wait. There is nothing else to do with the sea, so you do it as hard as you can: arm round the warm stone, rope twisted round your fist, eyes on the brown water at the edge of the roof.
>
> It climbs in breaths. A row of tiles goes under, and the water sits there, slapping, and then the next row goes. Something heavy comes past in the current, a door or a table top, turning slowly, and knocks against the gutter below you hard enough to shake the roof.
>
> The knock is what does it. Your boots are on wet tile, and wet tile is glass. The jolt goes through the roof and your feet go out from under you, and for a moment the only thing holding you to the house is the loop of rope round your fist. It snaps tight. Your arm comes off the chimney. You slide down the slope on your hip, three rows, four, until your boots are in the water and the rope is a bar of iron from your hand to the stone, and you stop.
>
> Tam Kemp is shouting something. His hands are on the rope above yours, pulling, which does nothing at all except make him feel better.
>
> You are still on the roof. Your legs are in the sea to the knee and the cold of it is unbelievable. The rope is cutting the back of your hand open again, and the water, steady and patient, is still rising past your shins.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 8 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

</details>

*State after: health 11/20, energy 0, XP 11, gold 9.*

## Turn 34 · The Chimney Roof

**Player:** "Brace your feet on the chimney and just hold it, Tam!" I go up the rope hand over hand, digging my boots into the tile seams, back to the stack.

> "Hold it!" you shout, and Tam Kemp does the one useful thing he has done all day: he jams both feet against the chimney stack, leans back on the rope, and holds.
>
> You go to climb. Hand over hand, you tell your arms, and your arms do not answer. There is nothing left in them. You have hauled yourself up a bank, a ramp, a boy out of a hole and a rubble slope today, and the cold of the water round your legs has taken the rest. You get one hand above the other and dig a boot into a tile seam, and the boot slides, and the hand above opens on its own.
>
> You drop back to the end of the rope with a jerk that wrenches your side, the same place as before, and this time it is not a fish hook, it is a knife. The breath goes out of you in a grunt. For a moment the roof and the water and the sky all slide to the left.
>
> When they come back you are hanging where you were, waist-deep now, the loop round your fist the only thing holding you. Above you, Tam is still leaning on the rope with his face screwed up. He is not strong enough to pull you. He is strong enough to keep you.
>
> "I can't," he says, through his teeth. "I can't lift you. I can only hold."
>
> The water climbs another tile. Your body has nothing left to give it. You need to stop, and the sea is not going to let you stop.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 1 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: critical failure (critical failure)  ·  margin -11
- injury: {"kind": "self_injury", "limb": "side", "severity": true, "lasting": true, "health_delta": -2, "summary": "Botched Athletics: you hurt your side.", "combat_penalty": {"mobility": 0, "attack": -1, "defense": -1}}

</details>

*State after: health 9/20, energy 0, XP 11, gold 9.*

## Turn 35 · The Chimney Roof

**Player:** I keep my chin up out of the water and whistle the runners' call as loud as I can, then shout for Jocosa.

> You tip your head back until the water is at your ears and whistle. It comes out cracked and breathy, nothing like the call you can do on a good day, and you do it anyway, high then low, again and again. Then you shout her name until there is no more shout in you.
>
> "Jocosa! Jocosa Kettle!"
>
> Tam Kemp takes it up from the chimney, his voice going high and breaking. "Jocosa! Here! The roof with the stack!"
>
> For a long time there is only the slap of water and the creak of the rope. Then, from somewhere off to the left, among the roofs of the second row, the call comes back. Two notes. Close.
>
> She comes round the end of the next house standing on a door. It is a real door, black with weed, brass knob and all, and she is poling it across the flooded street with her long ash hook-pole the way the old harbour men poled barges, knees bent, grim as a gravestone. She has lost her hat.
>
> "Hold still, Mara's girl," Jocosa Kettle says, and lays the door alongside the roof with a bump. She reaches the hook out, catches you by the back of your collar like a sack of salvage, and heaves, and with Tam pulling on the rope from above, between the two of them they drag you up out of the water and over the edge of the door, where you lie on your face, streaming, on the weedy wood.
>
> "I said two rows," she says, breathing hard. "Not this."

<details><summary>Engine</summary>

- weather: Weather shifts to Steady storm.

</details>

*State after: health 9/20, energy 0, XP 11, gold 9.*

## Turn 36 · The Chimney Roof

**Player:** I get my breath back on the door. "Will this carry three? Where's high enough to sit out a storm?"

> The rain arrives while you are still lying on your face on the door: big cold drops first, then a grey slant of it across the flooded rows, hissing on the water and drumming on the roof tiles. The wind comes with it, out of the sea, and the door rocks under you.
>
> Jocosa Kettle does not look at you. She is watching the water and the sky, both.
>
> "It'll carry three if nobody moves and nobody's stupid," she says. "So it'll carry two and a half." She shoves the pole down, finds bottom somewhere far below, and holds the door against the roof edge with her whole weight. "High enough? Nothing in the rows. The water's still coming."
>
> She jerks her chin out toward the sea, the way you have been trying not to look. Through the rain, beyond the last roofs, the broken customs tower stands up out of the water alone, square and black, with spray bursting white against its foot.
>
> "Stone tower, three storeys of it above the old high-water. That's the only thing out here built to stand in the sea, because it was." She spits rain. "And it's the wrong way. Out, not in. Into that."
>
> She does not say what she thinks you should do. She has the look of someone who has decided she has already done more than enough today, and is waiting to be told she is wrong.
>
> Tam Kemp is untying himself from the chimney with shaking hands.

<details><summary>Engine</summary>

- check: You rolled 8 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -1

</details>

*State after: health 9/20, energy 0, XP 11, gold 9.*

## Turn 37 · The Chimney Roof

**Player:** "The tower, then. Tam, sit in the middle and don't move." I hold out my purse to Jocosa. "Nine coin. All I have. Pole us out there."

> Tam Kemp gets himself off the roof and onto the door on his backside, the bad shin held out stiff in front of him, and settles in the very middle of it with his arms round his knees. The door sinks a hand's width and rights itself. He does not move.
>
> Jocosa Kettle looks at the purse in your hand for a long moment, rain running off the end of her nose.
>
> "Mara lent me eleven coin the winter my man died," she says. "Never asked for it back. Never got the chance." She pushes your hand and the purse back against your chest with two fingers, hard. "Put that away before it goes in the sea. It's the tower."
>
> She says nothing else. She sets the butt of the hook-pole against the roof's gutter and shoves, and the door slides out from the house into the flooded street, rocking, slapping, low in the water. Rain hammers on the three of you. She finds bottom with the pole, leans, finds it again, and the drowned houses begin to go by on either side, roof after roof, chimney after chimney, and between them the brown water running hard toward the land.
>
> Ahead, through the rain, the customs tower stands up dark and square over the last of the rows, with the open sea beyond it white to the horizon.
>
> "Feet in," Jocosa says. "Hands in. If we tip, hold the door, not each other."

<details><summary>Engine</summary>

- check: You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: success (barely)  ·  margin +0

</details>

*State after: health 9/20, energy 0, XP 11, gold 9.*

## Turn 38 · The Chimney Roof

**Player:** As Jocosa poles us out toward the tower, I keep my feet in and one hand on the door's edge, watching the water ahead for anything floating at us.

> You keep your feet in and your hand on the door's edge and watch. It is a better job than it sounds. The flood is full of the drowned district: shutters, a cradle, a whole thatch of reeds turning like a raft, barrels, and once a dead dog, legs up, going past with great dignity toward Saltmarrow.
>
> The door swings. The beam slides past under the water, a long black shadow, and grates against the edge of the door with a noise that goes through all three of you.
>
> Tam Kemp has his eyes shut. You do not blame him.
>
> The last row ends without warning, as if someone had cut it off with a knife, and then there is nothing between you and the tower but open water. Here it is not running toward the land but heaving, slow and grey, in long swells that lift the door and drop it. Jocosa stops trying to find bottom and uses the pole as a paddle, swearing steadily under her breath.
>
> The tower comes up out of the rain. Close to, it is bigger than you thought: dressed stone gone green to the height of a house, an arched doorway half drowned at its foot, and above, a row of narrow windows and the broken crown where the bell-chamber used to be. Spray bursts against the seaward side. On the landward side, out of the worst of it, an iron ladder runs up the wall from the waterline to the first window.
>
> Jocosa drives the door in under the ladder and hooks a rung with the pole.

<details><summary>Engine</summary>

- Dropped 2 line(s) of speech the narration gave the player that the player did not say.
- quest: Step done: Raise the customs-house bell (Sign for the contract)
- dice: xp (small): 1d6+2 [3] +2 = 5
- check: You rolled 12 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +0
- dice: player.xp_delta band small -> 5

</details>

*State after: health 9/20, energy 0, XP 16, gold 9.*

## Turn 39 · The Chimney Roof

**Player:** I can't climb yet. I rest on the door under the ladder, one hand hooked through a rung, and get some strength back while Jocosa holds us steady.

> You hook your arm through the lowest rung of the iron ladder and let the rest of you go slack against the door. That is all. You do not climb. You do not do anything. Your body takes the chance like a dog taking a dropped crust, and for a while the world is just the cold rung in the crook of your elbow and the door rising and falling under you.
>
> Jocosa Kettle holds the door against the tower with the pole hooked over a rung and her boots braced, and makes it clear she is doing it.
>
> "Rest, she says," she mutters to the rain. "In a sea storm. Under a tower. Holding a door with one stick." The swell lifts you all and drops you and the pole creaks. "Your mother would have been up that ladder already. Then again, your mother's not here, is she."
>
> Tam Kemp has fallen asleep sitting up, which seems impossible and is not.
>
> The storm goes on over your heads. Waves boom against the seaward side of the tower and you feel them through the stone and the iron and the door, a slow heavy heartbeat. In the lee it is almost quiet. The rain thins a little. Your breathing slows down until it is just breathing again.
>
> You are not rested. But you are less empty than you were.

<details><summary>Engine</summary>

- check: You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -10

</details>

*State after: health 9/20, energy 0, XP 16, gold 9.*

## Turn 40 · The Chimney Roof

**Player:** I wait an hour here under the ladder.

> You wait. An hour under a ladder in the lee of a tower is a long time, and the sea uses all of it.
>
> The storm wears itself out slowly, the way a crying child does: the gusts come further apart, the rain goes from a hammering to a hiss to a drizzle, and the boom of the waves on the seaward stones softens to a long thudding sigh. The swell under the door gentles. Jocosa Kettle gets the pole hooked properly over a rung and sits down on the edge of the door at last with her back to the tower and her eyes shut.
>
> "Mara used to say the sea would come back one day," she says, after a long time. "Everyone laughed at her for it."
>
> Tam Kemp wakes, looks around at the water, and remembers. He does not say anything. He shuffles closer to you on the door until his shoulder is against yours, and stays there.
>
> By the end of the hour the cloud has lifted off the horizon and there is a strip of watery light out to sea. The water is not going down. It is not coming up any more either. It is just there, a whole sea where the flats were this morning, as if it had never been away.
>
> Your arms have stopped shaking. The ladder looks like a ladder again, not a cliff.

<details><summary>Engine</summary>

- check: You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +1

</details>

*State after: health 9/20, energy 0, XP 16, gold 9.*

## Turn 41 · The Chimney Roof

**Player:** !wait 120 sleep

> You sleep. You do not mean to. One moment you are watching the strip of light on the horizon and the next it is gone, and the storm has come back over the top of you while you were away, and you are waking to the drum of rain on your back and someone's elbow in your ribs.
>
> It is Tam Kemp's elbow. He is asleep too, curled against you on the door like a dog against a stove. The two of you have been keeping each other alive in your sleep, and neither of you knew.
>
> Jocosa Kettle has not slept. She sits on the door's edge where she sat before, pole hooked over the ladder rung, oilskin collar up, rain running off her in sheets. She looks older than she did this morning, and much more tired.
>
> "Two hours," she says when she sees your eyes open. "Storm came back an hour in. Nothing came by but timber and a drowned sheep." She nods at the ladder above you. "Water's held where it was. Hasn't dropped a hand."
>
> You take stock. Your knee is stiff and your side is a hot bar under the ribs, and the hand the rope cut has puffed up purple. But your arms answer when you ask them. Your legs will hold you. There is something in you again that was not there before you slept.
>
> Above you the iron ladder runs up the wet green stones to the dark square of the first window.

<details><summary>Engine</summary>

- wait: Slept 120 minute(s). frontier dark fantasy · Day 1 · 12:45 → frontier dark fantasy · Day 1 · 14:45. Events: 0.

</details>

*State after: health 9/20, energy 11, XP 16, gold 9.*

## Turn 42 · The Customs Tower

**Player:** I climb the iron ladder up to the first window of the customs tower and go in.

> The ladder is iron, old and flaking, bolted into the stone with staples as thick as your thumb, and every rung is slick with weed and rain. You go up it the way you went up the rope: one hand, one foot, one breath at a time. Your side protests every reach. The knee does not bend well, so you lead with the other one. Halfway up a staple shifts in the wall with a grinding noise and holds.
>
> "Don't you dare fall on my door," Jocosa Kettle calls up. It is not affection. She sounds tired of the lot of you. "I'm not fishing you out twice in a day."
>
> The first window is a narrow arch with no glass, just a stone sill worn smooth. You get your arms over it and pull, and then you are in, sliding over the sill onto a stone floor that is dry. Dry. The first dry thing your body has touched since the morning.
>
> It is a single square room, dim, with a stone stair spiralling up one corner into the dark. Old customs ledgers rot on shelves along one wall, swollen like loaves. On the floor there are footprints in the grit, small ones and big ones, and they are not old. They lead to the stair and up.
>
> Below the sill, the door bumps against the tower foot. Above you, very faintly, up the stair, something metal ticks in the wind. Tick. Tick.

<details><summary>Engine</summary>

- weather: The steady storm breaks; sky eases toward clear.
- fact: The customs tower's first-floor room is dry; fresh small and large footprints in the grit lead up the spiral stair.
- check: You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -5

</details>

*State after: health 9/20, energy 10, XP 16, gold 9.*

## Turn 43 · The Customs Tower

**Player:** I lean out of the window and call down: "Tam, come up. It's dry." Then I take the stair, following the footprints up toward the ticking.

> Your voice goes down into the rain. A moment later the ladder starts to clank, slow and uneven, and Tam Kemp comes up it one-legged, swearing at every rung in words his aunt would skin him for. You leave him to it and take the stair.
>
> It turns tight round a stone newel, worn hollow in the middle of every step. The footprints go up ahead of you in the grit: a big boot, heel-heavy, and beside it a small bare foot, a child's or a slight woman's, with the toes spread wide the way runners' toes go after years on the mud. The ticking gets louder as you climb.
>
> The second floor is one room like the first, but it is not empty. Someone has been living in it, or working in it. There is a table made from a door laid on two barrels, a lantern with a little oil left in it, a pile of tarred sacking for a bed. And on the table, ticking, is a machine.
>
> It is brass, the size of a bread loaf, with a glass face and a ring of channel names scratched round the edge in a small, careful hand you know as well as your own. Its needle is turning, slowly and steadily, round and round. Under it, held flat by a stone, is a sheaf of paper covered in columns of figures and dates, years of them, in the same hand.
>
> Your mother's hand.
>
> Behind you Tam reaches the top of the stair, breathing hard, and stops.

<details><summary>Engine</summary>

- system: Followed the footprints with no place named; the player stayed in The Customs Tower.
- fact: The customs tower's second floor holds a working brass tide machine and years of tide figures in Mara Tarrow's handwriting; someone has been living there recently.

</details>

*State after: health 9/20, energy 10, XP 16, gold 9.*

## Turn 44 · The Customs Tower

**Player:** I lift the stone off the papers and read the newest page, the last date first.

> You lift the stone off. The top sheet is the newest, and the last line on it is today's date.
>
> The figures above it go back down the page in a long careful column: dates, hours, channel names, and beside each a mark in a second column headed *bar*. You have never seen the word used like that. The marks start small at the top of the page and creep wider down it, day by day, until the last few are long dark strokes that run off the edge of the column.
>
> Under the last figure, in the same hand, written fast:
>
> *Sea over the outer bar at first light, three hours before the reckoning. H. Jocosa Kettle says the reeve will move the mark and say nothing. The bell must be rung. If he will not ring it, I will.*
>
> Tam Kemp has slumped down against the wall by the stair with his bad leg stuck out in front of him.
>
> "It's just numbers," he says when you look up. He does not want to know, and he says so with every line of him. "I want to go home. I want to tell Aunt Philippa I'm not dead, and I want to get dry, and I don't care about anybody's numbers."
>
> Above your head, through the timber ceiling, something shifts. A step, light and bare, on old boards. Then nothing.

<details><summary>Engine</summary>

- fact: Mara Tarrow's newest tide note is dated today: the sea crossed the outer bar three hours early; 'H.' said the reeve would move the mark and say nothing; she wrote that the bell must be rung, and she would ring it if he w
- check: You rolled 4 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -9

</details>

*State after: health 9/20, energy 8, XP 16, gold 9.*

## Turn 45 · The Customs Tower

**Player:** I go up the last of the stair, slow and quiet, toward that step. "Mam?"

> The stair narrows as it climbs, until your shoulders brush stone on both sides, and then it opens out under the sky.
>
> This is the top of the tower, what is left of the bell-chamber: four stone arches open to the wind, the roof long gone, rain blowing straight through. In the middle a great oak frame stands empty, its iron bearings rusted bright orange. The bell is not in it. The bell is on the floor, on its side in a nest of rope and timber rollers, as if someone has been trying, a little at a time, to move something no one person could move.
>
> There is a woman beside it.
>
> She is thin, burnt dark by wind, barefoot, in a runner's oilskin patched so many times it is more patch than skin. Grey hair cut short with a knife. She has a mallet in one hand and an iron wedge in the other, and she has stopped dead with both raised, looking at you. Her jaw is your jaw.
>
> She does not say anything. Her mouth opens, and nothing comes out of it, and she lowers the mallet very slowly, the way you would lower it near a bird you did not want to frighten off.
>
> Below you, Tam Kemp calls up the stair, his voice thin and worried.
>
> "Isk? Who's up there? Who is it?"

<details><summary>Engine</summary>

- Verifier replaced npcs.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- quest: Step done: Raise the customs-house bell (Reach the old customs house)
- check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +4

</details>

*State after: health 9/20, energy 8, XP 16, gold 9.*

## Turn 46 · The Customs Tower

**Player:** I don't move. "It's Isk. It's me, Mam. Mara Tarrow, it's me." Then, louder, down the stair: "It's all right, Tam. It's my mother."

> At your voice the woman flinches as if the name were a stone thrown at her. Then the mallet slips out of her hand and lands on the boards with a dull knock, and the wedge after it.
>
> She does not speak. She comes across the bell-chamber in four steps, barefoot over the wet timbers, and stops an arm's length from you, and looks. At your face. At the purple hand. At the brass reckoner hanging from your belt on its old cord. She reaches out and touches the reckoner's case with one finger, the way Jocosa touched the red cloth on the lamp pole, and her breath goes out of her in a long shudder.
>
> Then she has hold of you, both arms, hard enough to hurt your side, smelling of tar and salt and lamp smoke, and she is shaking, and so are you.
>
> Below, Tam Kemp has gone quiet. When he speaks again his voice has changed.
>
> "Your mother?" he says up the stair. "But she's on the lamp. The red one. Everybody knows she's on the lamp." A pause. "Is she real? Isk, is she really real?"
>
> Over your shoulder, past the empty bell-frame and the arches and the rain, the sea lies flat and grey to the end of the world. Your mother, Mara Tarrow, holds on to you and does not let go.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- dice: xp (moderate): 2d6+6 [4, 6] +6 = 16
- check: You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +6
- dice: player.xp_delta band moderate -> 16

</details>

*State after: health 9/20, energy 8, XP 32, gold 9.*

## Turn 47 · The Customs Tower

**Player:** "Six years, Mam. Why didn't you come home?"

> Mara Tarrow lets go of you enough to look at your face. Her mouth works. Nothing comes out of it but breath, a dry rasp like a door that has not been opened in years, and she shuts it again and shakes her head, angry with herself.
>
> She turns, instead, and points. Past the bell, out through the seaward arch, at the grey flat water where the flats used to be. Then at the bell lying on its rollers. Then at you. Then she presses her hand flat to her chest and holds it there, hard.
>
> Tam Kemp has come up the last turn of the stair on his backside, one step at a time, and is sitting in the stair-head looking at her as if she might be a drowned thing come back.
>
> "Don't ask me," he says, sharp with fright, when you look round at him. "How should I know why? I thought she was dead same as everyone. Philippa Kemp Ask her." He looks at Mara's hand on her chest, and his voice drops. "She can't, can she. She can't talk."
>
> The rain has stopped. Somewhere below, the swell knocks against the tower's foot, slow and patient, like someone at a door who knows you are home.

<details><summary>Engine</summary>

- check: You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -8

</details>

*State after: health 9/20, energy 8, XP 32, gold 9.*

## Turn 48 · The Customs Tower

**Player:** I take Mara's hand off her chest and hold it. "You don't have to talk. Show me. Is the bell why you stayed?"

> Mara Tarrow looks down at your hand round hers for a long moment. Then she nods, once, hard, and pulls you by it across the bell-chamber to a beam by the stair-head where a stub of charcoal hangs on a string.
>
> The beam is covered in writing. Tally marks, dates, channel names, all the way along it, years of them, and under them a clear space she must have kept for something. She takes the charcoal and writes in it, in big plain capitals, pressing so hard the stick snaps halfway through and she goes on with the stub.
>
> REEVE PAID ME TO WATCH THE SEA. SECRET. H. CAME EACH MONTH. TOOK MY FIGURES. BROUGHT FOOD.
>
> She stops, breathing hard, and writes again underneath.
>
> I TOLD THEM IT WAS COMING. HE SAID HE WOULD WARN THE TOWN. HE NEVER DID.
>
> She draws a hard line under that, and then she turns and points at the bell on its rollers, and at the empty oak frame above it, and makes a pulling motion with both fists, as if on a rope. Her eyes are fierce and wet.
>
> On the stair, Tam Kemp reads the beam over your shoulder with his lips moving. "H.," he says slowly. "Jessop. The tide clerk. He comes out to the tower? I've seen him going down the stairs at dry tide with a basket. Everybody thought he was fishing."

<details><summary>Engine</summary>

- fact: The reeve secretly paid Mara Tarrow to watch the sea from the customs tower; Hereward Jessop fetched her figures monthly. She warned that the sea was returning; the reeve never warned the town.
- check: You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: success (barely)  ·  margin +2

</details>

*State after: health 9/20, energy 8, XP 32, gold 9.*

## Turn 49 · The Customs Tower

**Player:** "Then we ring it. Here, now, before the next water." I look at the bell, the frame and her rollers. "Show me how you meant to get it back up."

> It is Tam Kemp who answers, from the stair-head, before Mara can move. He has been looking at the rollers the whole time, the way a carter looks at a load.
>
> "She's done the hard bit," he says, and pulls himself up by the newel to see better. "Got it off the frame and onto rollers without cracking it. But you'll never lift that by hand. Not three of us. Not ten." He points with his chin at the top beam of the oak frame, where a great iron hook still hangs. "You go over that. Rope through the hook, down to the bell's crown, and back down to something you can walk round. That." He nods at a stone bollard in the floor by the seaward arch, worn smooth by old mooring lines. "Turn it like a capstan, bit by bit, wedge it every turn so it can't run back."
>
> Mara Tarrow has gone very still, watching him. Then she crosses to the wall and drags out from under the sacking two coils of old line, grey and stiff with salt, and a short iron bar. She lays them at your feet beside your own tarred rope and looks at Tam, and at you, and nods.
>
> "Your rope's the best of them," Tam says. "Hers'll do for the wedging." He swallows. "My uncle moved a millstone like that once. I watched him."
>
> Outside, the light is going toward evening, and out on the grey water a long low line of white is gathering again along the bar.

<details><summary>Engine</summary>

- check: You rolled 13 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +1

</details>

*State after: health 9/20, energy 8, XP 32, gold 9.*

## Turn 50 · The Customs Tower

**Player:** I climb the oak frame, pass my tarred rope through the iron hook, tie the end fast to the bell's crown, and run the other end down to the stone bollard.

> The oak frame is old and black and sound, and it takes your weight without a creak. You climb it the way you climbed the ladder, careful of the knee, and lie along the top beam with your arm hooked over it. The iron hook up close is as long as your forearm, rusted rough, and the tarred rope goes through it with a hiss and a smell of pitch.
>
> You let the end down to the bell, climb down after it, and kneel on the wet boards beside the great bronze lip. Up close the bell is green-black with weather, cast with letters round the shoulder that the sea has worn too smooth to read. You pass the rope through the crown loops and tie it off with the best knot you know.
>
> Tam Kemp watches you from the stair-head with his arms folded and his lip out.
>
> "Not that knot," he says. "That's a sack knot. That'll slip the minute it takes the weight, and then it's down on its lip and cracked, and you've got no bell and no thirty coin." He does not offer to come and do it. "Do the one with two turns. Round and round and through."
>
> You run the free end across the floor to the stone bollard and take a turn round it. The rope lies there in a long sag, hook to bell, bell to bollard, ready.
>
> Mara Tarrow kneels by the bell and puts her hand on your knot, and looks at you, and very slightly shakes her head. Tam is right.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -1

</details>

*State after: health 9/20, energy 5, XP 32, gold 9.*

## Turn 51 · The Customs Tower

**Player:** "Fine. Two turns." I untie my sack knot and tie it again the way Tam says, round and round and through, and pull it hard to set it.

> You pick your own knot apart with numb fingers, the wet tar fighting you, and tie it again the way he said: round the crown loop, round again, back through both turns, and then you lean your whole weight back on the line to set it. It bites down on itself and goes hard as wood.
>
> Tam Kemp watches you do it, and somewhere in the middle of the second turn his folded arms come unfolded.
>
> "That's it," he says. "That's the one." And then, as if it has been surprised out of him: "My uncle said a knot's the only thing on a cart that'll tell you the truth." He pushes himself up off the stair-head on his good leg and hops across the boards to the bollard, wincing at every hop, and takes hold of the line behind you. "Right. You and me on the bar. She does the wedges. She's got the eye for it."
>
> Mara Tarrow is already kneeling by the bell with the short iron bar and a fistful of oak wedges, looking up at Tam with an expression you have not seen on her yet. It takes you a moment to know it. She is trying not to smile.
>
> The line runs taut now from bollard to hook to bell, humming a little in the wind through the arches.

<details><summary>Engine</summary>

- check: You rolled 20 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: critical success (critical success)  ·  margin +11

</details>

*State after: health 9/20, energy 5, XP 32, gold 9.*

## Turn 52 · The Customs Tower

**Player:** Tam and I set the iron bar against the bollard and walk the line round it a turn at a time, while Mam knocks in a wedge after every turn.

> You set the iron bar in the notch of the bollard and lean into it, and Tam Kemp leans beside you on his one good leg, and the bollard turns. A hand's width. The rope creaks through the iron hook overhead. Mara Tarrow slams an oak wedge into the bollard's foot, and you both let go and breathe.
>
> Again. A hand's width. Wedge. Again.
>
> On the fifth turn the bell's lip comes up off the rollers. On the eighth it swings free, a hand above the boards, turning slowly on its rope, and the whole bell-chamber hums with it, a deep sound under your feet that is not quite a note.
>
> Tam stops pushing. He is looking at the bell hanging there, and his face has gone hard.
>
> "You're going to ring it," he says. "Here. And then what? It's no use to the guild once it's hung back in this frame, is it? Nobody gets the thirty coin." His voice climbs. "I signed for it first. I nearly drowned for it. My uncle's cart's at the bottom of the fish market because of that bell, and you're going to hang it back up where nobody can sell it and bang on it like a fair-day drum."
>
> He lets go of the bar entirely. The bollard groans, and Mara's wedge holds, just.
>
> "I'm not turning that for nothing," he says. "Not one more turn."

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 1 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: critical failure (critical failure)  ·  margin -8
- blunder: Botched Persuasion / Speech: you say the one thing they did not want to hear.

</details>

*State after: health 9/20, energy 5, XP 32, gold 9.*

## Turn 53 · The Customs Tower

**Player:** "If that bell isn't rung, there's no town left to sell it to, Tam. Your aunt's in that town." I hold out my purse. "Take my 9 coin toward a new cart. And I'll stand with you in front of Una and your aunt and say you signed first."

> Tam Kemp looks at the purse in your hand for a long moment. Then at the bell, turning slowly on its rope a hand above the boards. Then out through the landward arch, where in the far distance, low on the grey water, the roofs of Saltmarrow show above the flood like a row of teeth.
>
> "Aunt Philippa's chandlery is on the wall," he says, very quietly. "It's on the lowest bit of the wall."
>
> He takes the purse. He does it fast, as if he is afraid one of you will change your mind, and stuffs it inside his wet shirt without counting it. Nine coins. All you had. You feel the lightness at your belt at once.
>
> "Doesn't make us square," he says. He will not meet your eyes, and his voice is still sharp with something, fear or shame or both. "A cart costs forty. And you'd better say it. In front of Una. That I signed first." He limps back to the bollard and sets both hands on the iron bar. "And if it cracks when you ring it, that's on you."
>
> Mara Tarrow kicks the wedge free.
>
> You lean on the bar together. The bollard turns. The bell rises, a hand's width, then another, the rope groaning through the hook, and the deep hum in the floor climbs with it.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- dice: gold (small): 2d6+3 [4, 2] +3 = 9, lost (-9)
- check: You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +3
- dice: player.gold_delta band small -> -9

</details>

*State after: health 9/20, energy 4, XP 32, gold 0.*

## Turn 54 · The Customs Tower

**Player:** We keep turning the bollard, a turn and a wedge, until the bell's crown is up under the frame's beam, and I guide it into the iron bearings.

> Tam Kemp Turn and wedge. Mara Tarrow Turn and wedge. Your arms burn and then stop burning and go somewhere past it. Tam Kemp works beside you without a word now, his jaw set, and Mara Tarrow moves round the bollard on her knees with the wedges and the bar, never missing one.
>
> The bell climbs. It turns slowly as it goes, and as it turns the letters round its shoulder catch what is left of the light, and for a moment you can almost read them.
>
> When its crown is a hand under the top beam you leave the bar to Tam and climb the frame again, and lean out over the drop with your bad hand on the beam and your good one on the cold bronze, and guide it. The iron bearings on its shoulders are rusted orange. The sockets in the frame are rusted orange. They meet with a grinding, shrieking scrape that sets your teeth on edge, and then a deep clunk that goes down through the whole tower like a door shutting.
>
> The bell hangs in its frame.
>
> Tam lets go of the bar. He does not cheer. He sits down where he is, on the wet boards by the bollard, and puts his face in his hands.
>
> "Don't talk to me," he says through his fingers when you look down at him. "Just ring the thing."
>
> Mara is looking up at the bell with her mouth open and her hands pressed flat together in front of it.

<details><summary>Engine</summary>

- dice: xp (moderate): 2d6+6 [2, 4] +6 = 12
- check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6
- dice: player.xp_delta band moderate -> 12

</details>

*State after: health 9/20, energy 4, XP 44, gold 0.*

## Turn 55 · The Customs Tower

**Player:** I take the bell rope Mam has tied to the clapper and ring it. Hard. Again and again, toward Saltmarrow.

> Mara Tarrow has knotted a length of her old grey line to the clapper's ring, and it hangs down beside the frame to the height of your hand. You take it.
>
> The first stroke is nothing. The clapper swings, heavy and slow, and kisses the bronze, and a dull wooden sound comes out like a fist on a door. On the third stroke the bell wakes.
>
> It is not a sound so much as a weight. It comes out of the bronze and fills the bell-chamber and goes on through the stone into your feet, into your teeth, into the old ache of Tidecount along your jaw. It goes out through the four arches over the water in every direction at once, and the water carries it. Again. Again. You lean your whole body on the rope and the bell swings up and rolls over and speaks, and each stroke goes out over the drowned flats toward the low dark line of Saltmarrow's roofs.
>
> Tam Kemp has stood up. He has both hands over his ears and he is laughing, or crying, or both.
>
> You ring until your arms quit. When you stop, the last stroke goes on humming in the bronze for a long time, and then, very faint and very far, from across the water, another bell answers. Thin and high and frantic. The temple bell on the wall at Saltmarrow, rung by someone who heard.
>
> Then lights. One, two, ten, a scatter of lanterns along the harbour wall, moving.

<details><summary>Engine</summary>

- Dropped 2 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- dice: xp (large): 3d8+16 [4, 3, 7] +16 = 30
- event: Isk rang the customs bell from the tower; Saltmarrow heard and answered with its temple bell.
- check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +10
- dice: player.xp_delta band large -> 30

</details>

*State after: health 9/20, energy 3, XP 74, gold 0.*

## Turn 56 · The Customs Tower

**Player:** !wait -1 sleep

> You sleep in the bell-chamber on Mara's tarred sacking, all three of you in a heap against the landward wall out of the wind, with the bell hanging dark and quiet above you.
>
> You wake once in the night. The sky has cleared and there are more stars than you have ever seen, and out across the water, where the rows were, there are lamps. Small yellow lights, a dozen of them, two dozen, hung on poles and chimneys among the drowned roofs, bobbing very slightly. The Lantern Wives have rowed out, or waded out, or come some way you cannot imagine, and lit them all. For whoever is still out there. You lie and watch them until they blur.
>
> Mara Tarrow is awake too. She is sitting with her back to the frame and her mother's-hand charcoal in her fingers, not writing, just watching the lamps, and when she sees your eyes are open she reaches out without looking and puts her hand on your hair, the way she did when you were small. Then you are asleep again.
>
> Morning comes up grey and gold over a flat sea. Tam Kemp is snoring. Your body has stiffened into one solid ache from heel to jaw, the knee and the side and the torn hand all complaining at once, but under the aches there is strength again, more than you have had since the bank.
>
> The water has not gone down. In the clean light, the flats are simply gone, and Saltmarrow stands at the edge of a sea.

<details><summary>Engine</summary>

- weather: Weather shifts to Light fog.
- wait: Slept 817 minute(s). frontier dark fantasy · Day 1 · 16:23 → frontier dark fantasy · Day 2 · 06:00. Events: 0.

</details>

*State after: health 9/20, energy 15, XP 74, gold 0.*

## Turn 57 · The Customs Tower

**Player:** I stand in the landward arch and use Tidecount on the new sea. Does it go out again today, or is it here to stay?

> You stand in the landward arch with the morning wind in your face and let Tidecount come.
>
> It comes differently now. For all your life it has been one thing: a cold pressure that said how long until the water came back to the flats. This morning there is no coming back. The water is here. What you feel instead is the water breathing: a long slow pull outward, and a long slow push back in, deep under the surface like a sleeper's chest.
>
> It will go down. Not to mud. Not to the flats you knew. But around midday it will draw back far enough that the roofs of the higher rows stand clear by a man's height, and the harbour wall at Saltmarrow will show its old mooring rings dry again for an hour or two. Then it will come in. Twice a day, the way the old songs say the sea did before the Leaving.
>
> Not the wrong hours any more. The right ones. The sea has remembered how to be a sea.
>
> Behind you Tam Kemp has woken and is sitting up in the sacking, rubbing his eyes, looking at your back.
>
> "You're doing the jaw thing," he says. "Your face goes like that. Like toothache." A pause. "What's it saying?"
>
> Mara Tarrow is watching you too, with her charcoal in her hand, as if she already knows and wants to hear you say it.

<details><summary>Engine</summary>

- fact: Tidecount, day two at dawn: the returned sea keeps true tides twice daily; low water around midday bares the higher rows' roofs and Saltmarrow's mooring rings for an hour or two.
- check: You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +5

</details>

*State after: health 9/20, energy 14, XP 74, gold 0.*

## Turn 58 · The Customs Tower

**Player:** "It's a real tide now, Tam. Twice a day, like the old songs. Low water at midday, and we go home on it." I turn to Mam. "All of us."

> "Like the old songs," Tam Kemp repeats, as if he is not sure he heard right. Then, slowly, his face changes. "So the wall's a harbour again. Aunt Philippa's chandlery's on a harbour." He almost laughs. "She'll be selling rope to boats."
>
> Mara Tarrow does not move when you turn to her. She looks past you at the brass machine ticking on its table by the stair, and at the beam of figures, six years of them, and at the bell. Her hand tightens on the charcoal until it snaps again. She looks like someone standing at the top of the harbour stairs, not sure the next step will hold.
>
> Then Tam is at the seaward arch, pointing, his voice cracking up high.
>
> "Boat! There's a boat coming out!"
>
> It is a real boat, a long low harbour skiff that must have been sitting dry in somebody's shed for forty years, rowed by two men, with a third standing in the stern. It is coming out from Saltmarrow over the flat morning water, straight for the tower, quickly. The man in the stern is thin and wears a clerk's dark coat, and even at this distance you can see he is holding a slate under one arm.
>
> Mara has seen him too. She goes very white, and very still.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 15 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +4

</details>

*State after: health 9/20, energy 14, XP 74, gold 0.*

## Turn 59 · The Customs Tower

**Player:** I go down to the first window and wait for the boat. When it bumps the ladder I call down: "Hereward Jessop. You came for her figures again?"

> The skiff comes in under the tower's lee and bumps the iron ladder, and the two rowers ship their oars and sit looking up at the bell-chamber the way people look at a church roof. Hereward Jessop stands in the stern with his slate clutched to his coat. He looks as though he has not slept at all.
>
> At your voice he flinches, and then he looks up, and sees you in the window. And behind your shoulder, on the stair, Mara Tarrow.
>
> "No," he says. It comes out hoarse. "Not her figures. Not this time." He wets his lips. "The reeve sent me. He heard the bell, the whole town heard the bell. He said take it down before the guild sees it hung, and bring the woman in quiet, and say she was a madwoman squatting in the tower." He looks at the slate in his hands as if he has never seen it before, and then, very deliberately, he drops it over the side. It goes into the water without a splash. "I've been chalking his lies on that wall for six years. I'm done."
>
> One of the rowers says something low and angry. Hereward does not turn round.
>
> "Mara," he says up to the window, and his voice breaks on her name. "I told him. Every month I told him. I'm sorry. I'm so sorry. Will you come down? Will you let me take you home?"

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.

</details>

*State after: health 9/20, energy 15, XP 74, gold 0.*

## Turn 60 · The Customs Tower

**Player:** I step back from the window so Mam can see him, and take her hand. "It's yours to choose, Mam. I'll go wherever you go."

> Hereward Jessop hears you from the boat, and his face goes tight and miserable.
>
> "She won't," he says flatly, before Mara can move. "I know her. She'll stay up there with her clock till the sea takes the tower too. I've asked before. Every month I asked." He sits down heavily on the stern thwart. "Ask her yourself if you like. You'll get the same as I did."
>
> Mara Tarrow lets go of your hand.
>
> She turns away from the window and goes back up the stair, barefoot and quick, and you hear her moving about above you in the bell-chamber, the scrape of the door-table, the clink of the brass.
>
> When she comes down again she has the brass machine wrapped in sacking under one arm and the whole sheaf of papers inside her oilskin, held flat against her chest. She stops at the window beside you and looks down at Hereward in the boat with an expression you cannot read at all.
>
> Then she takes the stub of charcoal from behind her ear and, on the stone sill of the window, in letters for him to see, writes one word.
>
> TOWN.
>
> And she swings her leg over the sill onto the ladder.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -5

</details>

*State after: health 9/20, energy 15, XP 74, gold 0.*

## Turn 61 · Saltmarrow

**Player:** I climb down the ladder after Mam into the skiff and help Tam down after me. "Take us home, Hereward."

> The skiff rocks as you drop into it, and again as Tam Kemp comes down the ladder after you on his good leg and his backside and sits down hard in the bilge. Mara Tarrow is already in the bow with her wrapped machine in her lap, looking straight ahead at the town.
>
> Hereward Jessop looks at you for a moment when you say it. Then he nods once and turns to the rowers.
>
> "You heard her. Home."
>
> The rowers bend to it. The tower falls away behind you, square and black, with the bell a dark shape in its crown. The drowned rows go by on either side, roofs and chimneys standing up out of the clear morning water, and here and there on a pole or a chimney a Lantern Wives' lamp, burnt out now, swinging. Nobody speaks. The oars knock and dip.
>
> Saltmarrow grows. It is not the town you left. The harbour wall stands with its feet in the sea for the first time in forty years, waves slapping at the old mooring rings, and all along the top of it there are people, a crowd of them, more than you have ever seen on the wall at once. Someone sees the skiff and shouts, and the shout runs along the wall like fire along a fuse.
>
> The skiff comes in against the bottom of the harbour stairs, which go down now not into mud but into water. Hereward catches a ring and holds the boat steady, and the stairs go up in front of you to the crowd at the top.

<details><summary>Engine</summary>

- check: You rolled 17 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +4

</details>

*State after: health 9/20, energy 14, XP 74, gold 0.*

## Turn 62 · Saltmarrow

**Player:** I get Tam's arm over my shoulder and we go up the harbour stairs together. At the top I look for Philippa in the crowd.

> The harbour stairs are wet to the fourth step and dry above it, and you go up them with Tam Kemp's arm across your neck and his whole weight on you every other step. Behind you Mara Tarrow climbs with her bundle held to her chest, and behind her Hereward Jessop, hat in his hands.
>
> At the top the crowd opens and closes round you like water. Faces you have known all your life, and every one of them turned to the sea, and then to you, and then past you, to the thin barefoot woman on the stair. Somebody says Mara's name, not loud. Then somebody else says it, louder.
>
> You look for Philippa and do not have to. She comes out of the chandlery door at a run, apron and all, shoving through the crowd with her elbows, and stops dead a yard from Tam with both hands over her mouth.
>
> Tam lets go of you. He stands on his own on his one good leg, swaying, soaked and filthy and fourteen.
>
> "I lost the cart," he says. "I'm sorry, I lost Uncle's cart."
>
> Philippa Kemp makes a noise that is not a word and takes hold of him so hard he yelps.
>
> Wulfstan the weaver is beside you at the wall's edge, his skein forgotten in his fist, staring at Mara.
>
> "The bell," he says to you, low. "We heard the bell. Half the wall was down on the steps watching the water come. The reeve's men were telling us to go home and stop gawping." He swallows. "Was that you?"

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- quest: Tam Kemp came home to Saltmarrow alive; Philippa met him on the wall.
- check: You rolled 17 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +7

</details>

*State after: health 9/20, energy 13, XP 74, gold 0.*

## Turn 63 · Saltmarrow

**Player:** "It was me. And my mother." I raise my voice so the wall can hear. "Mara Tarrow's been in the customs tower six years, measuring the sea for the reeve. He knew it was coming back. He paid her to watch, and he told none of you."

> Your voice carries further than you expected. The wall goes quiet in a ring around you, and the quiet spreads, and for a moment there is only the slap of the sea at the foot of the wall.
>
> Then the muttering starts, and it is not what you hoped. Some of it is anger, but not much, and not yet. Most of it is the other thing. *Tarrow's girl. Lost her mother on the flats. Grief turns you.* A woman near the front says loudly that Mara Tarrow drowned six years ago, she saw the red cloth go up herself, and whoever that is on the stair, it's not her. A man laughs. Someone says the reeve has been good to this town.
>
> Mara Tarrow stands at the top of the stairs with her bundle against her chest and does not move. She cannot answer them. You see her understand that, all at once, and her face closes.
>
> Wulfstan puts a hand on your arm. He does not look at you. He is looking past you, down the wall toward the reeve's end of the harbour, where the crowd is parting for a knot of men in the reeve's grey.
>
> "That's a story for a full belly and a warm room," he says, very low, flat and unconvinced. "Not for the wall, with his men coming. You've no proof but a woman who can't talk and a boy who'll say anything for his aunt."
>
> He takes his hand back.
>
> "If you've got it written down, you'd better have it written down well."

<details><summary>Engine</summary>

- check: You rolled 8 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -1

</details>

*State after: health 9/20, energy 13, XP 74, gold 0.*

## Turn 64 · Saltmarrow

**Player:** I turn round to the stair. "Hereward Jessop. You carried her figures every month. Tell them."

> Hereward Jessop is still at the top of the stairs with his hat crushed in his hands. Every face on the wall turns to him. You watch him understand what you are asking, and what it will cost, and you watch him decide.
>
> He climbs onto the stone bench by the tally board where he has stood every morning for six years to chalk the tides, and he faces the crowd.
>
> "She's telling you true." His clerk's voice is thin, but the wall is so quiet it carries. "That's Mara Tarrow. She didn't drown. The reeve found her on the outer bar six years ago, half dead, and he put her in the customs tower and paid her to watch the sea, because she said it was coming back and he believed her." He wets his lips. "Every month I rowed out at dry tide with her food and came back with her figures, and every month the reeve read them and locked them in his chest. And every month he had me chalk you a tide on that wall that was a lie."
>
> Nobody moves.
>
> "He knew this week. He knew yesterday morning. I told him myself, at first light." Hereward's voice cracks. "He said if the town panicked the guild would lose its runners and the harbour would lose its taxes. He said wait. So I chalked you two hours, and I went home."
>
> At the reeve's end of the wall, the men in grey have stopped pushing through the crowd. The crowd has closed up in front of them, and is not opening.

<details><summary>Engine</summary>

- event: Hereward Jessop publicly confessed that the reeve hid Mara Tarrow's warnings and chalked false tides.

</details>

*State after: health 9/20, energy 13, XP 74, gold 0.*

## Turn 65 · Saltmarrow

**Player:** I ask Mam for her papers with a look, and when she gives them to me I pin them up on the tally board, over the guild contracts, where everyone can read them.

> Mara Tarrow understands the look. She unbuttons the oilskin with stiff fingers and puts the sheaf of papers into your hands without letting go of them for one long moment, and then she lets go.
>
> The tally board is covered in guild contracts, the customs bell still pinned highest of all with its red thumbprint. The column headed *bar* creeping wider and wider down every page until the last strokes run off the edge.
>
> The crowd presses in to read. People who cannot read crowd in behind people who can, and the ones in front read aloud. A runner's voice, an old woman's, a boy's, all reading figures, dates, *sea over the outer bar*. You hear the town learn it. It moves through the crowd like the cold moved through your bones in the channel.
>
> Hereward Jessop gets down off the bench to stand by the board, and he points to a page without a word, and to another.
>
> Wulfstan reads the last sheet twice, the one dated yesterday, and then he turns to the crowd and holds it up over his head.
>
> "Written down well enough for me," he says, loud now.
>
> Somebody, at the back, says the reeve's name. Not kindly. Then everybody is saying it.

<details><summary>Engine</summary>

- weather: The light fog breaks; sky eases toward clear.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- dice: xp (moderate): 2d6+6 [3, 3] +6 = 12 · karma (moderate): 1d4+2 [2] +2 = 4
- check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +5
- dice: player.xp_delta band moderate -> 12
- dice: player.karma_delta band moderate -> 4

</details>

*State after: health 9/20, energy 13, XP 86, gold 0.*

## Turn 66 · Saltmarrow

**Player:** I stay by the board with Mam and wait for the reeve's men to come to us. I'm not hiding.

> You stay where you are, at the tally board, with your back to your mother's figures and your mother at your shoulder, and you watch the grey coats come.
>
> The crowd does not part for them now. It shifts, and shoves, and grumbles, and the reeve's men have to come through it shoulder first, and the press of bodies swings back against the board like a tide against a wall. Someone big is pushed into you from the side. The edge of the tally board's frame catches you under the ribs, on the side that is already hurt, and the breath goes out of you in a white flash that leaves you holding on to the board with both hands.
>
> When you can see again there are four of them in front of you, in the reeve's grey with brass at the collar, and the crowd has drawn back a pace to watch.
>
> Wulfstan has not drawn back. He has stepped up beside you, skein and all, which you would never have expected.
>
> "She's not going anywhere," he tells them, though you have not said a word. "Neither are these." He jerks his head at the board. "You want them down, you'll have to take them down in front of all of us. Go on, then."
>
> Hereward Jessop says nothing. He has moved to stand on your other side, and his hands are shaking, and he does not move.
>
> The leading man in grey looks at the board, and at the crowd, and does not reach for anything.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 5 with your base of 10 (dexterity) and a modifier of +0 (attr +0 + skill +0 (un | Result: failure (unskilled mishap)  ·  margin -9
- injury: {"kind": "self_injury", "limb": "ribs", "severity": false, "lasting": false, "health_delta": -1, "summary": "Botched Stealth: you hurt your ribs.", "combat_penalty": {}}

</details>

*State after: health 8/20, energy 12, XP 86, gold 0.*

## Turn 67 · Saltmarrow

**Player:** "Fetch the reeve," I tell the man in front. "He can answer for his own tides. Here, at the board, in front of everyone."

> The man in grey looks at you for a long moment. Then he looks at the crowd, which is very close and very quiet, and he turns on his heel without a word and shoves back the way he came. The other three go after him.
>
> "He'll come," Hereward Jessop says beside you, low. "He'll have to. He can't let it stand on the board with the whole wall reading it." He wipes his mouth with the back of his hand. "He'll come smiling."
>
> "Then we'll see the smile," Wulfstan says, and spits over the wall into the sea.
>
> It does not take long. The crowd at the reeve's end parts, properly this time, and a big soft-bodied man in a good dark coat comes down the wall with the four grey men at his back. He is bareheaded and his hair is oiled flat and he is, as Hereward said, smiling: a broad, sorry, patient smile, like a man coming to deal kindly with a child who has broken something.
>
> "Reeve Baldwin Thorne," Hereward says under his breath, as if you might not know. Everyone knows.
>
> Thorne stops in front of the board. He does not look at the figures. He looks at Mara, standing barefoot at your shoulder, and the smile goes thin for a moment, and comes back.
>
> "Mara," he says warmly. "Mara, my dear. You should be resting."

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 14 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +1

</details>

*State after: health 8/20, energy 12, XP 86, gold 0.*

## Turn 68 · Saltmarrow

**Player:** "Don't talk to her like that." I take the last page off the board and hold it out to Reeve Thorne. "Read it to them. Out loud. Then tell them why you moved the tide two hours instead of ringing the bell."

> Baldwin Thorne looks at the page in your hand. He does not take it. He looks at it the way he might look at a fishmonger's bill: with patience, and a little pity.
>
> Then he does take it, gently, between finger and thumb, and holds it up so the crowd can see it. And he tears it in half. And in half again. The pieces go over the wall into the sea and float, white, on the slack water.
>
> The crowd makes a sound like a wave drawing back over shingle.
>
> It is Hereward Jessop who speaks, and his voice is not thin any more.
>
> "There's six years of those on the board," he says. "Tear them all. You'll be at it till noon, and every man on this wall will watch you do it." He turns to the crowd. "That was yesterday's. I'll tell you what was on it. Sea over the outer bar at first light, three hours early. He had it in his hand by breakfast. He had me chalk you two hours."
>
> Thorne's smile does not move, but something behind it does.
>
> "Hereward," he says mildly, "you're overwrought."
>
> "Read it, then," says Wulfstan, very loudly, from your other side. "The next one. Go on. There's a nail full of them."

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -9

</details>

*State after: health 8/20, energy 13, XP 86, gold 0.*

## Turn 69 · Saltmarrow

**Player:** I hand Mam the charcoal from behind her ear. "Tell them yourself, Mam. On the board."

> It is Baldwin Thorne who answers you, quickly, kindly, stepping half between you and the board.
>
> "Now, now. Let the poor woman be." He spreads his soft hands. "You can see the state of her. Six years alone on the bar. She doesn't know what day it is, let alone what she's writing. Mara, my dear, give the girl back her charcoal and come along home with me, and we'll get you warm."
>
> Mara Tarrow looks at him. Then she steps round him as if he were a post on the wall, and goes to the tally board, to the one clear stretch of plank at the bottom where nothing is pinned, and writes.
>
> She writes big, so the back of the crowd can read it. The charcoal squeals on the wet wood.
>
> I KNEW THE DAY. I WROTE IT DOWN. HE READ IT. HE SAID WAIT.
>
> She stops. Her hand is shaking. Then she writes one more line under it, smaller, and steps back so everyone can see.
>
> MY NAME IS MARA TARROW. I AM NOT MAD. I WAS RIGHT.
>
> Nobody laughs this time. A woman near the front, the same one who said Mara drowned, puts her hand over her mouth.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +3

</details>

*State after: health 8/20, energy 13, XP 86, gold 0.*

## Turn 70 · Saltmarrow

**Player:** When the whistling dies down I say it plain to Baldwin Thorne: "You don't get to keep the tides any more. Hereward and my mother keep them now. Out loud, on this board, every day."

> Baldwin Thorne looks at you for a long time. The smile is gone now. What is under it is tired and very calculating, a man adding up a column he does not like.
>
> "Out loud," he says at last. "On a board." He glances along the wall, at the faces, at the four men in grey who have somehow drifted to the back of the crowd. "Very well. Let the clerk chalk his tides, and let the madw—" He stops himself. "Let Mistress Tarrow write her figures beside them. The town can read them both and drown as it likes."
>
> He straightens his good coat.
>
> "But you'll answer to the guild, Tarrow's girl, not to me. That bell was salvage under contract. Your name's in Una Rendle's book for it. The guild will want its bell on the tally floor, not hanging in a tower for anybody to bang on." He nods to the board, to the guild sheets you pinned your mother's pages over. "And the guild has a long memory for debts."
>
> He turns and goes, and the crowd lets him, and the men in grey go after him at a distance that says a good deal.
>
> Behind you, very quietly, Hereward Jessop lets out a breath he seems to have been holding for six years.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- dice: xp (moderate): 2d6+6 [4, 2] +6 = 12
- check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (barely)  ·  margin +2
- dice: player.xp_delta band moderate -> 12

</details>

*State after: health 8/20, energy 13, XP 98, gold 0.*

## Turn 71 · The Tally House

**Player:** I go to the tally-house window with Tam and ring the cracked hand bell. When Una opens up I tell her: "The customs bell's hung back in its tower and rung, and it stays there. I'm giving up the contract. And put it in your book that Tam Kemp signed first."

> You leave the board to Hereward and the crowd and walk the wall to the tally house, Tam Kemp limping at your side. The cracked hand bell clanks twice. The shutter goes up.
>
> Una Rendle has been watching from the window all along; there is charcoal dust on her sleeve from leaning on the sill. She hears you out without a word. Then she pulls the long ledger from under the counter and lets it fall open at the customs bell.
>
> Your name is at the bottom, still dark. Above it, written big, the way Tam said: Tam Kemp.
>
> Una dips her pen. Beside your name she draws a single neat line, and in the margin writes *contract surrendered, bell rung for the town*. Then she moves the pen up the page to Tam's name, and stops, and looks at the boy for a long moment.
>
> She does not cross him out. She writes beside him, small and careful, *signed first*, and blots it with the side of her hand, and turns the ledger round so Tam can see it.
>
> Tam reads it twice. His ears go red.
>
> Una closes the book and leans on it.

<details><summary>Engine</summary>

- quest: Quest abandoned: Raise the customs-house bell
- check: You rolled 16 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +8

</details>

*State after: health 8/20, energy 14, XP 98, gold 0.*

## Turn 72 · The Tally House

**Player:** "Una. I owe the tallyman a winter's credit. Is that in your book too?"

> Una Rendle does not even open the ledger for that one. She knows it the way she knew the customs page.
>
> "Fourteen coin," she says. "Winter credit, rope and oil and two sacks of meal, at the guild rate. Due at the new moon." She taps the closed book with one finger. "It's in here, and it stays in here. You surrendering a contract doesn't wipe a debt, and ringing a bell for the town doesn't either. The guild's not the town."
>
> Una glances past you along the wall, to where your mother's figures hang on the board, and her mouth goes thin.
>
> "And if you're thinking of your mother's share, the one the guild kept when they wrote her down as lost, that's a matter for the guild masters, not for me at a window," she says. "Mara Tarrow's share was paid into the lost-runners' fund six years ago, with everybody else's. If she wants it back she can stand in front of the masters and say she's not dead." She almost smiles, and does not. "Which, by the look of the wall this morning, she's well able to."
>
> Behind you on the bench by the door, a grizzled regular in a salt-stiff coat has been listening to every word with his pipe going out.
>
> Una pulls the shutter halfway down.
>
> "New moon. Fourteen coin."

<details><summary>Engine</summary>

- Verifier replaced narration.
- fact: Isk owes the salvage guild fourteen coin of winter credit, due at the new moon; Mara's lost share sits in the guild's lost-runners' fund.
- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

</details>

*State after: health 8/20, energy 14, XP 98, gold 0.*

## Turn 73 · Saltmarrow

**Player:** I go along the wall to Philippa's chandlery to find Tam and Mam, and see if there's somewhere to sit down.

> "Go and sit down before you fall down," Una Rendle says through the half-shut window as you turn away. It is not unkind. "You look like something the tide brought in."
>
> You walk the wall back to the chandlery. The crowd has thinned to knots of people talking low, reading the board, looking out at the water. The door of Philippa Kemp's General Store is propped open with a coil of anchor chain.
>
> Inside it is warm. Someone has lit the stove in the back. Tam Kemp is sitting on a flour barrel with his bad leg up on a crate and a bowl of something steaming in his lap, eating like a starved dog. Philippa Kemp is kneeling in front of him wrapping his shin in clean linen, and talking without stopping, scolding and fussing and scolding again, and every so often she stops talking to put her forehead against his knee.
>
> Your mother is sitting very straight on the bench by the stove with a blanket round her shoulders and a cup between her hands, looking at the shelves of rope and oil and wicks as if she had forgotten such things existed.
>
> Philippa looks up and sees you in the doorway. She gets to her feet without a word, takes a second bowl off the stove, fills it, and puts it into your hands. Then she points at the bench beside Mara.

<details><summary>Engine</summary>

- venue_redirect: Philippa Kemp's General Store is entered from Saltmarrow; the journey ends there.
- check: You rolled 12 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +3

</details>

*State after: health 8/20, energy 14, XP 98, gold 0.*

## Turn 74 · Philippa Kemp's General Store

**Player:** I go into the chandlery, sit down on the bench beside Mam, and eat Philippa's stew.

> You duck back in through the chandlery door and sit down on the bench beside your mother, and the stew is hot and thick with barley and smoked fish, and for a while that is the whole world.
>
> Mara Tarrow watches you eat. After a while she takes one of your hands, the torn one, turns it over, looks at the rope burn across the back of it, and makes a small sound in her throat.
>
> Philippa Kemp stands at the stove with her arms folded, watching the pair of you. She has not sat down once.
>
> "Eat it all," she says. "There's more." Then, sharper: "And don't think a bowl of stew means I've forgotten. He signed for that bell because he heard it paid in coin. He nearly drowned in the fish market for a bell that was never going to the guild at all." She looks at Mara, not at you. "Six years she let us all think she was dead. Six years the Wives lit lamps for her."
>
> Mara's hand goes still on yours.
>
> Tam Kemp, on his barrel, says "Aunt," in a warning voice, and Philippa stops. She turns back to the stove and bangs the lid on the stew pot harder than she needs to. Her shoulders are shaking.

<details><summary>Engine</summary>

- check: You rolled 4 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -3

</details>

*State after: health 8/20, energy 12, XP 98, gold 0.*

## Turn 75 · Philippa Kemp's General Store

**Player:** "She didn't let us think it, Philippa. The reeve did. He found her half dead on the bar and kept her in that tower for his figures. She wrote to him every month that the sea was coming. Every month."

> Philippa Kemp stands with her back to you at the stove for a long moment. When she turns round her face is blotched and her eyes are wet and furious, but the fury has nowhere left to go.
>
> "Every month," she says.
>
> She looks at Mara Tarrow properly then, maybe for the first time: at the cropped grey hair, the bare feet, the blanket, the cup held in both hands like something precious. Something goes out of Philippa's shoulders.
>
> "I lit one of those lamps myself," she says, quieter. "The first winter. I stood out on the mud with Jocosa Kettle and the others, and I lit one for you, Mara. I thought you'd want one." She wipes her face with her apron, roughly. "Well. You'll have a bed upstairs, the both of you, until you've a roof of your own. I'll not hear otherwise."
>
> Then she turns to you, practical again, the way people are when they have cried enough in front of others.
>
> "And that cart. My Wat built that cart. If the water goes out at midday the way you say, it'll be lying in the fish market hole with half the sea gone off it. You bring it up whole, and I'll pay you what I'd pay any runner for a hard haul. Fifteen coin." Her mouth twists. "Which I hear is a coin more than you owe the guild."
>
> Tam, on his barrel, has gone bright red.

<details><summary>Engine</summary>

- quest: New job offered: Bring up Wat's cart (from Philippa Kemp)
- check: You rolled 17 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +10

</details>

*State after: health 8/20, energy 12, XP 98, gold 0.*

## Turn 76 · Philippa Kemp's General Store

**Player:** "Done. I'll bring Wat's cart up whole, Philippa. I'll take the job."

> Philippa Kemp nods once, sharp, the way she would close a sale on a coil of rope.
>
> "Midday, then. You'll want a boat to get out and a boat to bring it back on; a cart won't float far." She jerks her chin at the door, toward the stairs. "Hereward Jessop's skiff is still tied at the bottom. He owes this town a good deal of rowing, and he knows it."
>
> She goes to the shelf behind the counter and comes back with a coil of new hemp line, pale and stiff, and a pair of iron cart-hooks on a strap, and puts them on the counter in front of you.
>
> "On the house. Bring them back with the cart." Her voice catches, and steadies. "And bring yourself back, Mara's girl. One Tarrow coming home from the flats is all my heart's got room for this week."
>
> Behind her, Mara Tarrow has set her cup down and is watching you, with the look of someone who already knows you will go, and is trying to be glad of it.

<details><summary>Engine</summary>

- Verifier replaced narration.
- quest: Quest accepted: Bring up Wat's cart (from Philippa Kemp)
- dice: item_count (small): 1 +1 = 1 · item_count (small): 1 +1 = 1
- check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +9
- dice: item:new hemp line band small -> 1
- dice: item:iron cart-hooks band small -> 1

</details>

*State after: health 8/20, energy 12, XP 98, gold 0.*

## Turn 77 · Philippa Kemp's General Store

**Player:** !wait 180 wait

> The morning goes by in the chandlery the way mornings used to go by before any of this: the stove ticking, Philippa Kemp selling lamp oil and line across the counter to a steady trickle of people who mostly want to look at your mother, and Tam Kemp asleep on his barrel with his mouth open.
>
> You doze on the bench and wake and doze again. Mara Tarrow does not sleep. She sits with your old brass reckoner open in her palm, watching the needle, and every so often she makes a small mark with charcoal on the back of her hand.
>
> Toward the end of the morning a woman in a fish-scaled apron Ursula comes in for wicks and stays to talk, leaning on the counter with her voice lowered and her eyes on Mara the whole time. The guild masters are sitting in the guildhall with the doors shut, she says. Have been since the bell. And the reeve's house has its shutters up in broad daylight, and two of his grey coats were seen on the coast road at dawn with a laden mule, going inland.
>
> "Running," the woman says, with great satisfaction, and takes her wicks and goes.
>
> By the time the bell in the temple tower strikes eleven and then the half, the light through the door has gone white and high, and Mara gets up and goes to the door and looks out at the water, and holds up five fingers to you, and then closes them. Not long now.

<details><summary>Engine</summary>

- weather: Weather shifts to Steady wind.
- wait: Waited 180 minute(s). frontier dark fantasy · Day 2 · 08:36 → frontier dark fantasy · Day 2 · 11:36. Events: 1.
- rumor: The guild masters have been shut in the guildhall since the bell rang; the reeve's shutters are up and two of his men left inland at dawn with a laden mule.

</details>

*State after: health 8/20, energy 15, XP 98, gold 0.*

## Turn 78 · Philippa Kemp's General Store

**Player:** I take Philippa's line and the cart-hooks down the harbour stairs to Hereward's skiff. "Hereward. Row me out to the old fish market while the water's down?"

> Hereward Jessop is sitting on the bottom step of the harbour stairs with his boots in the water, staring at nothing, and he looks up when your shadow falls on him as if he has been waiting all morning for someone to give him something to do.
>
> "Row you," he says. "Yes." He is already untying the skiff. "Yes, I can row you."
>
> He has sent the two harbour men home. He takes the oars himself, badly at first and then better, and you sit in the stern with Philippa's coil of new line in your lap and the cart-hooks clinking at your feet. The sea is down. Mara was right to the half hour: the water has drawn back off the harbour wall and left the old mooring rings dripping in the sun, and out on the drowned rows the roofs stand clear by a man's height, the upper windows of the houses gaping dark and streaming.
>
> The rows go by. The lamp poles. A chimney with a rope still knotted round it.
>
> The fish market's long humped roof rises out of the water ahead, half its tiles gone. The sea has drawn back down its walls to the eaves. The doorway you crawled out of yesterday is a dark arch with the water lapping at its lintel, and inside, in the dim, something pale floats and turns slowly: the rope Tam tied under his arms, still knotted to nothing.
>
> Hereward ships his oars and lets the skiff drift in against the eaves.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- quest: Step done: Bring up Wat's cart (Reach the old fish market at low water)

</details>

*State after: health 8/20, energy 15, XP 98, gold 0.*

## Turn 79 · The Old Fish Market

**Player:** I climb out of the skiff onto the fish market's eaves and go in through the gap in the roof tiles, to find the hole where the cart went down.

> The eaves are slick with weed, but the roof slopes gently here and the gap in the tiles is wide enough to drop through. You go in feet first and land on a crossbeam, then lower yourself onto the stone counter you tied the rope to yesterday. It is above the water now, just. The hall below is a long dim pool, knee-deep and still, with the light falling through the broken roof in bars.
>
> The hole in the floor is easy to find. The water stands lower inside it than out, sucked down into whatever cellar lies underneath, and there at the bottom, a man's height down, lies Wat's hand cart on its side in a foot of black water, one wheel up.
>
> It is whole. The bed is unbroken, the iron tyres still on.
>
> "Is it there?" Hereward Jessop calls from the skiff outside, his voice echoing in under the roof. "Can you get at it?"
>
> He has brought the skiff round to the doorway and holds it against the lintel with an oar, peering in.
>
> "I can get the boat right in," he says. "Water's low enough. You hook it, I'll pull from the boat, the way you and the boy did with the bell."

<details><summary>Engine</summary>

- check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +6

</details>

*State after: health 8/20, energy 14, XP 98, gold 0.*

## Turn 80 · The Old Fish Market

**Player:** "Bring the boat in." I tie Philippa's new line to the cart-hooks, climb down into the hole, hook the cart by its axle, and pass the line up and out to Hereward.

> Hereward Jessop brings the skiff in under the doorway arch, ducking under the beams, and holds it off the counters with an oar. You knot Philippa's new line to the strap of the cart-hooks and lower yourself over the broken edge of the hole.
>
> It is further down than it looks. You drop the last of it and land knee-deep in black cold water on the cellar floor, and the stink of old fish and new sea comes up round you. The cart lies on its side beside you, half buried in silt.
>
> The axle is right there. You get the first hook on it, and the second, and haul on the line to set them.
>
> They slide. The axle is coated in a skin of slime from the cellar mud, and the iron hooks skate along it and come off the end with a clank and a splash. You try again, lower, nearer the wheel hub. Same. The line comes up slack in your hands, and the hooks hang off the end of it, dripping, useless.
>
> Above you, Hereward's face appears at the edge of the hole, upside down.
>
> "Nothing?"
>
> The water round your knees is cold, and it is not as low as it was a minute ago. Somewhere under the floor, very faintly, the sea has started to come back in.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 9 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -4

</details>

*State after: health 8/20, energy 11, XP 98, gold 0.*

## Turn 81 · The Old Fish Market

**Player:** Forget the hooks. I pass the line under the cart's bed and through the spokes of the low wheel, tie it off with Tam's two-turn knot, and shout up to Hereward to pull.

> You give up on the hooks. You pass the new line under the cart's bed, through the spokes of the low wheel, round again, and through both turns, Tam's knot, the one that tells the truth. Then you set your shoulder against the cart's side, plant your boots in the silt, and shout.
>
> "Pull!"
>
> Up in the skiff Hereward Jessop braces his feet on the thwart and hauls. The line goes tight over the broken edge of the floor and creaks. For a moment nothing moves but your boots, sliding backward in the muck. Then the silt lets go of the cart all at once with a sucking belch, and it rolls upright onto its wheels, and you are pushing it up the slope of fallen planks with the water pouring out through its boards.
>
> It takes forever and it takes about two minutes. The cart comes up over the lip of the hole and onto the floor of the hall, and Hereward, red in the face and laughing like a boy, ties the line off on the skiff's stern ring.
>
> You climb out after it. It stands there in the knee-deep water, streaming, black with mud, every board whole, the iron tyres rusted but sound. On the side of the bed, under the mud, someone long ago carved a W.
>
> "It'll float behind," Hereward says. "Wood floats. We'll tow it home on the tide."
>
> Under your feet, the sea is coming back in.

<details><summary>Engine</summary>

- weather: The steady wind breaks; sky eases toward clear.
- quest: Step done: Bring up Wat's cart (Raise the cart from the hole)
- dice: xp (moderate): 2d6+6 [2, 6] +6 = 14
- dice: player.xp_delta band moderate -> 14

</details>

*State after: health 8/20, energy 11, XP 112, gold 0.*

## Turn 82 · Saltmarrow

**Player:** I climb into the skiff beside Hereward and take one oar, and we row back to Saltmarrow on the rising tide with Wat's cart towing behind us.

> You climb into the skiff and take the bow oar. Hereward Jessop takes the stern, and between you, rowing badly and then less badly, you work the boat out from under the beams of the fish market and into open water, the line paying out behind until it comes taut and Wat's cart swings out of the doorway after you, riding low and heavy, its wheels just under the surface like a swimming dog's paws.
>
> The tide is coming in under you now, and it carries you. That is the trick of it, the one your mother knew and nobody else believed: the sea comes home twice a day and if you go with it, it does half the work. The roofs slide past. The chimneys. The lamp poles with their burnt-out lamps.
>
> It still takes the better part of an hour, and the cart drags at the line like a sulking child the whole way, and your bad side burns on every stroke. But the wall comes up ahead, with the mooring rings already half under again and faces along the top of it watching you come.
>
> One of the faces is Tam's. He has hopped all the way down to the bottom stair on his good leg and is standing there with the water at his ankles, staring past you at the thing on the end of the line.
>
> Hereward lays the skiff alongside the stair and grabs a ring.

<details><summary>Engine</summary>

- check: You rolled 15 with your base of 10 (intelligence) and a modifier of +0 (attr +0 + skill +0 | Result: success (barely)  ·  margin +0

</details>

*State after: health 8/20, energy 8, XP 112, gold 0.*

## Turn 83 · Saltmarrow

**Player:** Hereward, Tam and I haul Wat's cart up the harbour stairs and wheel it to the chandlery door. I hand Philippa back her new line and the cart-hooks. "Whole, like I said."

> Getting a waterlogged cart up a flight of wet stone stairs turns out to be a different thing from towing it. Hereward Jessop gets behind it with his shoulder to the bed, and Tam hops alongside giving orders nobody follows.
>
> You make four stairs. The cart is twice the weight it should be, every board full of sea, and on the fifth stair your bad knee folds under the load. The shafts jerk out of your hands. The cart rolls back down onto Hereward, who lets go with a yelp, and it goes bumping and clattering down the steps and stops with its back wheels in the water at the bottom, unbroken, streaming, exactly where it started.
>
> You sit down on the fifth stair with your knee throbbing.
>
> Up on the wall people have gathered to watch. Wulfstan leans over the parapet with his eternal skein of wool.
>
> "You'll want to let her drain first," he calls down. "Tip her on her side on the bottom stair and give it an hour. Then she'll be half the weight." He considers the cart. "And get more hands. There's six of us up here doing nothing but staring."
>
> Philippa's new line is still looped over your shoulder, and the cart-hooks clink at your belt.

<details><summary>Engine</summary>

- Verifier replaced narration.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- dice: skill_gain (trivial): 1 +1 = 1
- check: You rolled 5 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -4
- dice: skill:Athletics band trivial -> 1

</details>

*State after: health 8/20, energy 5, XP 112, gold 0.*

## Turn 84 · Saltmarrow

**Player:** I tip the cart on its side on the bottom stair to drain, then shout up to the wall: "Wulfstan's right. Who'll lend a hand in an hour? It's Wat Kemp's cart."

> You and Tam get the cart over onto its side on the bottom stair, and the sea pours out of it through the gaps in its boards in a dozen brown streams, back where it came from.
>
> When you shout up to the wall, it is Hereward Jessop who answers, from the stair below you, before anybody on the parapet can.
>
> "I'll get them," he says. "I'll get you twenty." He is already climbing, wiping his hands on his coat. "Wat Kemp carted my mother's coffin up the hill for nothing the winter she died. Half the wall owes Wat something. They just need asking by someone who isn't a Tarrow or a clerk." He stops on the stair and gives a small rueful laugh. "Well. By someone who isn't a Tarrow."
>
> He goes up into the crowd, and you watch him moving from knot to knot of people, talking low, pointing down at you and the cart. Faces turn. A big man in a cooper's apron nods. Two runners you know by sight start down the stairs. Wulfstan puts his skein of wool in his pocket for the first time in two days.
>
> The cart lies on its side on the bottom stair, draining, its wheels turning slowly in the wind off the water. W, it says, on the side of its bed.

<details><summary>Engine</summary>

- check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +11

</details>

*State after: health 8/20, energy 5, XP 112, gold 0.*

## Turn 85 · Saltmarrow

**Player:** With the hands Hereward found, we lift the drained cart up the stairs and wheel it along the wall to the chandlery door. I give Philippa back her line and the cart-hooks. "Wat's cart. Whole."

> With eight pairs of hands the drained cart is nothing. The cooper takes one shaft. People step out of the way. Somebody claps, and stops, embarrassed.
>
> You stop it at the chandlery door. Philippa comes out wiping her hands, and sees what it is, and stands very still. She puts one hand flat on the side of the bed, over the carved W, the way Mara put her hand on the reckoner.
>
> You lift Philippa's coil of line off your shoulder and the cart-hooks off your belt and hold them out. She takes them without looking at them. Then she goes back inside and comes out with fifteen coins in a twist of oilcloth, and presses them into your hand, and closes your fingers over them with both of hers, hard.
>
> Hereward Jessop is already backing away into the crowd, uncomfortable with the thanks that are not even his.
>
> "It was the town did that, not me," he says, too quickly, when you look at him. "I only asked. Don't make a thing of it." He jams his hat on. "I've a wall to chalk. Proper tides, now. Somebody has to."
>
> He goes, and you notice he walks straighter than he did this morning.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- quest: Quest complete: Bring up Wat's cart (from Philippa Kemp): +15 gold, +75 XP
- dice: item_count (small): 1 +1 = 1 · item_count (small): 1 +1 = 1
- check: You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -8
- dice: item:new hemp line band small -> 1
- dice: item:iron cart-hooks band small -> 1

</details>

*State after: health 8/20, energy 3, XP 187, gold 15.*

## Turn 86 · The Tally House

**Player:** I walk to the tally-house window, ring the cracked bell, and pay Una 14 coin for my winter's credit. "Line it out, Una. I don't owe the guild anything now."

> You walk the wall to the tally house on legs that have had enough of today, and ring the cracked bell. The shutter goes up at once. Una Rendle has been watching from the window, the way she watches everything.
>
> You count fourteen coins out of Philippa's twist of oilcloth onto the sill, one at a time, the way you counted three onto Philippa's counter yesterday morning. It feels like a year ago.
>
> Una counts them again with one finger. Then she pulls the long ledger out from under the counter, opens it at the winter credits, and finds your line without searching. She dips her pen and draws a single neat stroke through it, end to end, and blots it.
>
> "Paid," she says. She sweeps the coins into a tin. "Fourteen coin, winter credit, settled." She turns the book so you can see the line through your name, and then she does not turn it back at once.
>
> "There's been talk in the guildhall since the bell," she says, lower. "About Mara Tarrow's share in the lost-runners' fund. And about who pays a tide-reader, now there's a sea to read." She closes the ledger. "Nothing's decided. But your name came up, and not in the debt column."
>
> The shutter comes halfway down, and stops.

<details><summary>Engine</summary>

- Verifier replaced narration.

</details>

*State after: health 8/20, energy 2, XP 187, gold 1.*

## Turn 87 · The Tally House

**Player:** !wait -1 sleep

> You mean to go back to the chandlery. You sit down on the bench in the tally house porch for a moment to take the weight off your knee, out of the wind, and the moment is the whole afternoon and the whole night.
>
> You wake once in the dark to noise: along the wall the town is up late, singing, arguing, somebody playing a fiddle badly, people who have just found out the sea came back and cannot decide whether to mourn or celebrate and are doing both. Lanterns bob along the parapet. You sleep again.
>
> You wake the second time to a hand at your belt.
>
> It is light and quick, a thief's hand, feeling for a purse in the dark. A thin shape Hawise wrenches free and is off along the wall into the dark before you are fully awake, bare feet slapping on the stones. Your purse is still there when you feel for it. One coin, still there. You almost laugh.
>
> By dawn the wind has gone round into the east and turned colder, blowing off the land instead of the sea. The sky is clear and pale. Below the wall, the tide is out again, the mooring rings dripping, and out on the drowned rows the roofs stand up clear in the morning light.
>
> Somebody has put a blanket over you in the night. It smells of tallow and lamp oil. Philippa's.

<details><summary>Engine</summary>

- system: A notice is up: A debt of bread.
- wait: Slept 1019 minute(s). frontier dark fantasy · Day 2 · 13:01 → frontier dark fantasy · Day 3 · 06:00. Events: 3.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.

</details>

*State after: health 8/20, energy 15, XP 187, gold 1.*

## Turn 88 · Saltmarrow

**Player:** I fold Philippa's blanket over my arm and go along the wall into the chandlery to find Mam.

> The wall is quiet this early, littered with the night's leavings: a broken jug, a fiddle string, someone's shoe. You walk it with Philippa's blanket over your arm, past the tally board where Hereward has already chalked a fresh line in neat capitals, LOW WATER NEAR SIX AND SIX, and beside it, in your mother's hand, a small careful column of figures.
>
> The chandlery door is open. Philippa Kemp is behind the counter, measuring wick, and looks up at you over her spectacles.
>
> "There she is. Slept on Una's porch like a stray." She takes the blanket and folds it under the counter in one movement. "Your mother's been up since before the light. She's out on the bottom stair with Jocosa Kettle, the pair of them, staring at the water and not saying a word between them, which for Jocosa is a miracle and for your mother is all she's got."
>
> She lowers her voice.
>
> "Jocosa came at first light with her door and her pole. Said the tide's out and the lamp's showing, and somebody ought to take that red rag down before it rots on the pole." She looks at you. "She asked Mara if she wanted to go. Your mother wrote one word on Jocosa's hand with a bit of chalk."
>
> Philippa does not say what it was. She does not need to.

<details><summary>Engine</summary>

- venue_redirect: Philippa Kemp's General Store is entered from Saltmarrow; the journey ends there.
- check: You rolled 17 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +6

</details>

*State after: health 8/20, energy 15, XP 187, gold 1.*

## Turn 89 · Saltmarrow

**Player:** I go down to the bottom stair to Mam and Jocosa. "I'm coming with you to the lamp." I get onto Jocosa's door with them and we push off for the rows.

> Your mother and Jocosa Kettle are sitting side by side on the bottom stair with their feet in the water, not talking, the black weedy door bumping at the step beside them. Neither of them looks surprised to see you.
>
> It is Hereward Jessop who answers, from up on the wall by the tally board where he is chalking, leaning over the parapet with chalk on his fingers.
>
> "Three on a door again?" he calls down, not warmly. "You'll drown the lot of you and I'll have to chalk it." He goes back to his board. "Low water lasts an hour and a quarter. Not a minute more. I wrote it up there myself."
>
> Jocosa snorts. Mara Tarrow gets up, steps onto the door without a wobble, and holds out her hand to you.
>
> You get on. Jocosa pushes off with the pole, and the three of you slide out from the wall over the slack low water toward the rows. The roofs stand clear by a man's height, the upper windows streaming. The air is cold and very clean from the east.
>
> The two roofs come up ahead, the ones like a gate, and between them on its pole the old ship's lantern, smoked black, and under it the strip of faded red cloth, stirring in the wind.
>
> Jocosa grounds the pole on a gable ledge and holds the door still beneath it.

<details><summary>Engine</summary>

- check: You rolled 7 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

</details>

*State after: health 8/20, energy 15, XP 187, gold 1.*

## Turn 90 · Saltmarrow

**Player:** I hold the door steady against the gable with both hands and look at Mam. It's hers to take down.

> You set both hands flat against the green slates of the gable and hold the door there, and look at your mother.
>
> Mara Tarrow understands. She stands up on the door, steady as if it were stone, and reaches up the lamp pole. Her fingers find the knot under the old ship's lantern. It has been tied six years, and the salt has made it hard as wood, and she works at it patiently with her thumbnail while the door rocks gently under the three of you.
>
> It comes loose. The faded strip of red cloth falls into her hand.
>
> She holds it for a long moment. Then she does something you do not expect. She does not throw it in the sea. She folds it, small and neat, and puts it into Jocosa Kettle's hand, and closes Jocosa's fingers over it.
>
> Jocosa looks down at it. Her weather-beaten face does something complicated and private, and she turns it away toward the open water so neither of you can see.
>
> "Six years I lit this," she says to the sea, rough. "Every long ebb."
>
> Mara reaches up again and opens the little door of the old lantern. Inside there is a stub of candle and a twist of wick. She takes your hand and puts a flint and steel into it, from her oilskin pocket, and looks at you.

<details><summary>Engine</summary>

- dice: xp (small): 1d6+2 [2] +2 = 4
- check: You rolled 20 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: critical success (critical success)  ·  margin +9
- dice: player.xp_delta band small -> 4

</details>

*State after: health 8/20, energy 15, XP 191, gold 1.*

## Turn 91 · Saltmarrow

**Player:** I strike the flint over the wick until it catches, and light the lamp. "One more time. For nobody lost."

> The flint is old and the steel is rusty and the wind off the land keeps finding the gap in your cupped hands. You strike, and strike, and on the sixth strike a spark lands in the tinder and glows, and you breathe on it the way your mother taught you when you were small, and it takes.
>
> You put the tiny flame to the candle stub in the old ship's lantern. It gutters. It holds. A small yellow light stands up inside the smoked glass in the grey morning, absurd and brave, over the slack sea between the drowned roofs.
>
> Nobody needs it. That is the point.
>
> Mara Tarrow closes the lantern's little door very gently, as if it were a cupboard in a sleeping child's room. Jocosa Kettle has the folded red cloth in her fist and her face still turned away to the open water, and her shoulders are shaking, and she is not making a sound.
>
> Far off across the water, back at the town, a figure on the harbour wall is waving: Hereward at his tally board, both arms over his head, the way you would wave at a boat coming home. Beyond him the wall is lined with small shapes, watching the lamp.
>
> Under the door, the tide has turned. You feel it before you see it. The water has started, very gently, to come home.

<details><summary>Engine</summary>

- mechanics: Deterministic combat: unarmed vs B Hereward Jessop resolved as hit; damage 3; health 21->18/21.
- dice: xp (small): 1d6+2 [2] +2 = 4
- check: You rolled 14 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +5
- dice: player.xp_delta band small -> 4

</details>

*State after: health 8/20, energy 12, XP 195, gold 1.*

## Turn 92 · Saltmarrow

**Player:** We pole back to the wall on the turning tide. At the top of the stairs I walk Mam to the tally-house window. "Una. What did the guild decide?"

> Jocosa poles you home on the turning tide in silence, and the water carries you most of the way. At the top of the stairs you take your mother's arm and walk her along the wall to the tally house.
>
> The shutter is already up. Una Rendle is leaning on the sill with the long ledger closed under her elbows, and for once she does not wait to be asked.
>
> "The masters sat till midnight," she says. "Then they sent for me and the book." She looks at Mara Tarrow, straight at her, the first person in the guild to do so. "Mara Tarrow is written back in among the living. Your share from the lost-runners' fund comes back to you, six years of it, less nothing. The masters said that twice, so I'd write it right."
>
> She opens the ledger at a fresh page. It is blank except for a heading in her neat hand: TIDE-READER, CUSTOMS TOWER.
>
> "And this. The guild and the town both, half each, for once in their lives agreeing." Her finger rests under the heading. "Somebody to keep the customs tower and the bell. Read the sea, ring the high water and the low, post the figures on the board every day so the runners and the boats know. Four coin a week, and the tower to live in." She turns the book round and sets the pen beside it, between you and your mother. "They asked for Mara Tarrow. And they asked for her girl, who rang the bell."

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- quest: New job offered: Keep the tide tower (from Una Rendle)
- check: You rolled 16 with your base of 10 (intelligence) and a modifier of +0 (attr +0 + skill +0 | Result: success (success)  ·  margin +3

</details>

*State after: health 8/20, energy 11, XP 195, gold 1.*

## Turn 93 · Saltmarrow

**Player:** I look at Mam. She takes the pen first and writes her name, and I write mine under it. "We'll take it, Una. The tower and the bell."

> Mara Tarrow looks at the blank page for a long moment. Then she takes up the pen, and under TIDE-READER, CUSTOMS TOWER she writes her own name in her small careful hand, the hand from six years of figures, slowly, as if she is making sure of every letter. Mara Tarrow.
>
> She passes you the pen. You write yours under hers. Isk Tarrow. The two names sit there together on the clean page, one above the other, the ink still wet.
>
> Una Rendle turns the book round and reads them both. Then she blots them with the side of her hand, the way she does, and something at the corner of her mouth gives way at last.
>
> "Tide-readers," she says. "Written in. First new line on a clean page in this book for six years that isn't a debt or a death." She closes the ledger and keeps her hand flat on it. "The masters will want the high water rung tonight, so the boats know the bell means something. Four coin on the sill every seventh day. The tower's yours. Don't let it fall down."
>
> Behind you along the wall, Hereward Jessop has stopped chalking to watch. When you look round he lifts his chalk to you, like a man raising a cup.

<details><summary>Engine</summary>

- quest: Quest accepted: Keep the tide tower (from Una Rendle)
- dice: xp (moderate): 2d6+6 [3, 6] +6 = 15
- check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +10
- dice: player.xp_delta band moderate -> 15

</details>

*State after: health 8/20, energy 11, XP 210, gold 1.*

## Turn 94 · Saltmarrow

**Player:** Before we go out to the tower, I go into the chandlery to say goodbye to Tam and Philippa.

> The chandlery smells of tallow and the stove. Wat's cart stands just inside the door, drying, with its shafts propped on a crate, and somebody has already begun scraping the mud off the carved W.
>
> Philippa Kemp does not come out from behind the counter.
>
> "Goodbye, is it," she says, measuring wick and not looking up. "Out to a tower in the sea to live on gulls' eggs and charcoal. Well. Don't come crying to me when the roof leaks." She snips the wick too short and swears at it. "Go on, then. Go. I've customers."
>
> There are no customers. She does not look up again.
>
> Tam Kemp hops out from the back on his good leg with something in his fist. He holds it out to you without a word: your own purse, the one you gave him in the tower. It clinks. Nine coins.
>
> "Got the cart back," he says, gruff, red to the ears. "Didn't need the price of one after all." He shoves it into your hand and steps back fast, as if it might bite. "And I'll be out at the tower on the next low water, so don't think you're rid of me. Somebody's got to show you two how to tie a knot that tells the truth."
>
> Behind the counter, Philippa makes a sound that might be a laugh or something else, and blows her nose very loudly.

<details><summary>Engine</summary>

- venue_closed: Philippa Kemp's General Store is closed now (07:00-19:00).
- dice: gold (small): 2d6+3 [5, 6] +3 = 14
- check: You rolled 4 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -9
- dice: player.gold_delta band small -> 14

</details>

*State after: health 8/20, energy 11, XP 210, gold 15.*

## Turn 95 · The Customs Tower

**Player:** Mam and I go down the harbour stairs to Hereward's skiff, and he rows us out across the water to the customs tower.

> Una Rendle watches you go from her window, and as you pass the tally house she leans out.
>
> "High water's at half six tonight by Hereward's board," she says. "If I don't hear that bell by seven, I'll write you down as lost again, and this time I'll mean it."

<details><summary>Engine</summary>

- weather: Weather shifts to Cloudy.
- Ended the scene on the line spoken to the player; the prose had answered it for them.
- check: You rolled 6 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -3

</details>

*State after: health 8/20, energy 10, XP 210, gold 15.*

## Turn 96 · The Customs Tower

**Player:** I climb up the stair to the bell-chamber with Mam and use Tidecount on tonight's high water.

> The bell-chamber is as you left it: the bell hanging dark in its frame, the stone bollard with its wedges, the beam of charcoal figures by the stair. Your mother goes straight to her beam as if she has never been away.
>
> You stand in the seaward arch and let Tidecount come.
>
> It comes easy now, easier than it ever did on the flats: the cold ache along the jaw, and under it the long slow breathing of the sea. The tide is making. It will fill all day, steady, and stand at the top a little before half past six this evening, and tonight it will be a big one, bigger than last night's, the kind the old songs called a spring. It will come up the harbour stairs nearly to the wall.
>
> You turn round to tell her. Mara Tarrow is already looking at you with her head on one side, the charcoal in her fingers, and when you say half six she shakes her head, a short, stubborn, motherly shake, and points at the beam.
>
> At the bottom of the newest column, in her hand, written while you slept on Una's porch: 18.20.
>
> Ten minutes earlier than you felt it. She taps the figure twice, hard, and folds her arms. She does not look as though she is going to be argued with.
>
> The sea goes on breathing under the tower.

<details><summary>Engine</summary>

- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- fact: Tidecount, day three morning: spring high water this evening a little before half six; Mara's figures say 18.20.
- check: You rolled 8 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: partial (partial)  ·  margin -1

</details>

*State after: health 8/20, energy 7, XP 210, gold 15.*

## Turn 97 · The Customs Tower

**Player:** !wait 670 wait

> The day goes by in the tower the way you imagine all the days will go now.
>
> Your mother shows you the brass machine, and how its needle answers the sea, and how to read the bar column on her beam. You show her Tidecount, as well as you can, and she listens with her whole face, her hand over your jaw where the ache lives, as if she could feel it through the skin. You sleep for an hour in the afternoon sun on the sacking. You eat the bread and cheese Philippa pushed into your pack without a word.
>
> In the middle of the afternoon, while you doze, a skinny scavenger boy rowing a stolen washtub round the drowned rows comes up the iron ladder to see what is worth taking, and gets as far as your belt pouch before your mother sees him. She does not shout. She cannot. She picks up the mallet. The boy is down the ladder and away across the water in his tub before you are properly awake, and your purse is still on your belt.
>
> Your mother puts the mallet down again and looks at you as if to say: this is a tower in the sea, and people will come, and someone has to keep the door.
>
> The light goes long and gold. The tide fills. By the time the sun is low over the land, the water is high up the tower's green stones, higher than you have seen it, and the breathing of the sea has slowed almost to stillness.
>
> Mara stands at the beam with the charcoal, and looks at you, and at the bell rope.

<details><summary>Engine</summary>

- weather: The cloudy breaks; sky eases toward clear.
- wait: Waited 670 minute(s). frontier dark fantasy · Day 3 · 06:58 → frontier dark fantasy · Day 3 · 18:08. Events: 1.

</details>

*State after: health 8/20, energy 15, XP 210, gold 15.*

## Turn 98 · The Customs Tower

**Player:** At 18.20 by Mam's beam, I put her hand on the bell rope beside mine, and we ring the high water for Saltmarrow together.

> At twenty past six by the beam, the sea stops breathing in.
>
> The bell wakes slowly, the way it did the first time, a dull knock and then a deeper one, and then it rolls over in its frame and speaks. The sound goes out of the four arches over the high still water, over the drowned rows and the burnt-out lamp and the slack sea, all the way to the wall. You ring it slow and even, the way a high water should be rung, not the frantic warning of two days ago but a plain steady telling. Here is the top of the tide. Here is the hour. You can trust it.
>
> Across the water, small and clear, a lantern goes up on the harbour wall by the tally board. Then another. Then the whole wall, lantern after lantern, answering.
>
> You let the rope go. The last stroke hums on in the bronze.
>
> Beside you, Mara Tarrow is still holding the rope. She is looking at the lights on the wall, and her mouth is working, and then a sound comes out of her, rusty and cracked, a door that has not been opened in six years.
>
> "Isk."
>
> Just that. Your name, in your mother's voice.

<details><summary>Engine</summary>

- weather: Weather shifts to Light wind.
- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- quest: Quest complete: Keep the tide tower (from Una Rendle): +4 gold, +50 XP
- dice: xp (large): 3d8+16 [6, 3, 5] +16 = 30
- check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +6
- dice: player.xp_delta band large -> 30

</details>

*State after: health 8/20, energy 15, XP 290, gold 19.*

## Turn 99 · The Customs Tower

**Player:** I hold on to her. "I'm here, Mam. I'm not going anywhere. Say it again."

> It is too much, too soon. You see it land.
>
> Mara Tarrow goes rigid in your arms. Her mouth opens and the rasp comes again, and catches, and stops, and something like panic crosses her face, a woman reaching for a stair that is not there. She pulls away from you, hard, and backs off across the bell-chamber until her shoulders hit the oak frame, and stands there breathing fast with her hand pressed flat against her own throat.
>
> She shakes her head at you. Not sad. Angry. Angry at you for asking, and at herself, and at six years, all of it at once.
>
> Then she turns to the beam, snatches the charcoal off its string, and writes on the clear stretch under her figures, big and furious, the stick squealing on the wood.
>
> NOT YET.
>
> She draws a line under it so hard the charcoal snaps. And stands there with the broken stub in her fist and her back to you, shoulders heaving, looking out of the seaward arch at the dark coming in over the high still water.
>
> On the wall across the sea, the lanterns are still burning. The bell is still humming, very faintly, in its frame.
>
> Below the tower the tide stands at the top of its breath, and does not turn yet.

<details><summary>Engine</summary>

- Verifier replaced narration.
- system: Travel action with no MOVE op and no resolvable destination; player stayed put.
- check: You rolled 1 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: critical failure (critical failure)  ·  margin -12
- blunder: Botched Persuasion / Speech: you push when you should have waited.

</details>

*State after: health 8/20, energy 15, XP 290, gold 19.*

## Turn 100 · The Customs Tower

**Player:** I take a fresh stick of charcoal from Mam's box and, under her NOT YET, write my first line on the beam: today's date, high water 18.20, rung, answered.

> The box of charcoal sticks sits on the door-table by the brass machine. You take a fresh one. It is light and dry and leaves black on your fingers, the way your mother's fingers have been black for six years.
>
> Under NOT YET, in the clear stretch of the beam, you write. Your hand is not as small and careful as hers. The letters come out bigger and rougher, a runner's hand. Today's date. High water 18.20. Rung. Answered.
>
> It is the first line on the beam in any hand but hers.
>
> Mara Tarrow does not turn round. She stands in the seaward arch with her back to you and her arms wrapped round herself, as still as the oak frame, and whatever she is feeling she is keeping it out there with the sea, where you cannot see it. The silence between you is hard as a shut door. She has had six years of her own company and she is not giving it up for a daughter in three days, not tonight.
>
> Below the tower, in the last of the light, the tide turns. You feel it in your jaw before you see it: the long breath out beginning, slow and patient, the sea starting home the other way. Across the water the lanterns on Saltmarrow's wall go out one by one, as people go in to their suppers, trusting the bell to tell them when it matters.
>
> Out in the arch, your mother's shoulders, very slightly, let go.

<details><summary>Engine</summary>

- Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player.
- dice: xp (small): 1d6+2 [1] +2 = 3
- fact: Day three, 18.20: the first high water rung by the tide-readers Mara and Isk Tarrow; Isk's first line written on the beam.
- check: You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin -7
- dice: player.xp_delta band small -> 3

</details>

*State after: health 8/20, energy 15, XP 293, gold 19.*
