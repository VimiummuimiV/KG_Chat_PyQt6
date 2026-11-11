# Pets: Behavior

Pets roam along the strip above the input row. All behavior lives in `src/helpers/pets/`; rendering and mouse interaction are in `src/ui/chat/ui_pets.py`.
Distances below are given in "art pixels" (art px): on screen, this value is multiplied by the pet size from the settings (×2 by default).

## 1. Food Chain

```
grass ──> chicken ──> egg ──> rat
              ^
              │ prey
             fox ──(chases away)── dog
```

|---------------------|--------------------------------------|---------------------|------------------------|----------------------------|
| Pet                 | Role                                 | Eats                | Afraid of              | Leaves alone               |
|---------------------|--------------------------------------|---------------------|------------------------|----------------------------|
| Chicken (`chicken`) | herbivore, prey for foxes, lays eggs | grass (pecks at it) | foxes that are hunting | everyone else              |
| Fox (`fox`)         | predator                             | hunts chickens only | dogs                   | rats, snails, Clippy, dogs |
| Dog (`dog`)         | guard, protects against foxes        | nothing             | nobody                 | everyone except foxes      |
| Rat (`rat`)         | scavenger                            | broken eggs         | nobody                 | everyone else              |
|---------------------|--------------------------------------|---------------------|------------------------|----------------------------|
| Snail (`snail`),    |                                      |                     |                        |                            |
| Clippy (`clippy`)   | neutral, live independently          | nothing             | nobody                 | everyone                   |
|---------------------|--------------------------------------|---------------------|------------------------|----------------------------|

Grass and eggs are not pets; they are food on the strip.

## 2. Behavior Shared by All Pets

- **Random states** (when there is nothing else to do): `idle` (weight 5, 2–6 s), `walk` (5, 3–8 s), `walk_fast` (1, 1.5–3.5 s), `swipe` (1, 1.5–3 s), `with_ball` (2, 4–9 s), `lie` (3, 6–14 s; only dogs and foxes have this state). While walking, a pet has a 40% chance of turning around.
- **Running is never a random state.** A pet runs only when it has a reason: a fox stalking or fleeing, a dog chasing a fox, panic, or a chicken or rat going for food. With nothing to do, pets mostly rest, stand guard or stroll.
- **Speed** is tied to body length and animation pace: `walk` ×1, `walk_fast` ×1.6, `run` ×2.5. Enabling the "step-based" checkbox makes movement happen in short bursts timed to the steps.
- **Strip edges**: a pet turns around when it reaches an edge. A pet with a goal (running to or eating food, watching a race for food, stalking prey, chasing a fox) is only stopped by the edge and keeps facing its goal; turning it around every tick would fight the goal and make it jitter. A flying pet is not turned either: it bounces off the edge with half of its sideways speed.
- **Mouse**: clicking a pet triggers panic (runs for 1.2–2.2 s and forgets everything); click and drag to throw it—it flies and panics on landing. While it flies, the cursor is an obstacle (see section 10). Eggs can be picked up and rolled; grass cannot be picked up.
- **Redraw rate**: the strip is updated 30 times per second while everything stays on the ground and 60 times per second while any pet or egg is held by the mouse or in the air, so a thrown pet can be followed and hit. Both rates are set in the pet settings ("Strip, fps" and "Flight, fps"), from 10 up to 165 or the refresh rate of the fastest screen when that is higher. A higher rate costs processor time (every frame moves the pets and repaints their area); it does not need more memory, and the strip is painted by the processor, not by the graphics card. The timer is a precise one (`Qt.PreciseTimer`): the default coarse timer rounds the interval to the system clock step and makes the motion uneven. A held body is redrawn on every mouse move. Only what changed is repainted: a pet is invalidated when its place or its picture changed since the last frame, and a body outside the dirty area is not drawn at all. The mouse mask is the strip plus the bodies above it, so it is set again only when a body is in the air or leaves it.
- **Sight of food**: a pet notices food (grass, a broken egg) only within 160 art px on either side. Farther food does not exist for it, so a rat far from a broken egg never goes for it and the egg simply evaporates.
- **"Important" state**: panic, being held by the mouse, and flight. In these states, a pet notices nothing and does not react to anything.

## 3. Chicken

- Pecks at grass by running up to the nearest clump (reaction delay: 150–1500 ms). One clump = 4 pecks = one egg.
- Lays eggs while walking: once every 20–50 s of walking, if it has enough food for at least one egg (it starts with enough for one).
- To lay, the hen stops and sits down (`lay` animation, 1.6 s, played once). The egg leaves her tail at 40% of the animation, then she stands up and walks on in the same direction. While she runs for food or panics, laying waits; a scare or a fox interrupts it, and then no food is spent.
- If a fox is hunting and comes within 70 art px, the chicken runs away from it for 2–3.5 s.
- It will not run for food past a fox: if a fox is in the way, the chicken gives up on the food.
- It only goes for food it can actually reach: the food must leave room at one of its ends for the whole body of the hen inside the strip. If the nearer end is against an edge, she takes the other end; if neither fits, she ignores the food. A meal that becomes unreachable is dropped.
- If another pet is clearly going to reach the food first (by at least 0.5 s), the chicken stops and watches.
- A chicken carried off by a fox is replaced after half the average interval between predator visits. The new chicken enters from the edge farthest from the foxes, or, if there are no foxes, from the opposite edge to the one the previous chicken was carried off through.

## 4. Grass and Eggs

**Grass** grows only while there is at least one chicken. There are no more than 2 clumps per chicken. A new clump appears every 10–25 s (the more chickens, the more frequently). Eaten clumps disappear; when the last chicken disappears, all the grass is removed.

**Eggs** fall from a chicken's tail (drawn behind the pets, so a laid egg lies behind its hen) and roll according to the shape of the strip. They break on a hard landing (being thrown or falling from a height of about 75 px). An intact egg remains for up to 90 s, then cracks on its own once it is almost motionless. A broken egg remains for 8 s (time spent being eaten does not count), then evaporates. Only pets with the `eat` animation—that is, rats—can eat eggs, and only when they are broken. If there are no rats, eggs simply crack and evaporate.

## 5. Rat

- Runs to a broken egg it sees (within 160 art px) and eats it from the edges, taking a quarter per bite.
- The first rat to arrive and "claim" an egg gets to eat it; the others give up or watch.
- When there are no eggs, it behaves according to the usual random states.
- Foxes and dogs leave it alone, and it leaves them alone too.

## 6. Fox

A fox is a wild predator that lives not on the strip, but "around the corner."

**Visits.** The first visit is 3–10 s after being enabled. After that, the interval between visits is N seconds ±30%, where N is set in the settings ("Predator visits every, s"; default 45, range 5 to 1800; the slider is visible when foxes are enabled). It enters from a random edge and initially walks inward.

**If there are chickens on the strip** (free, not being held or in flight):
1. **Stalking**: walks toward the nearest chicken, reassessing which one is nearest on every tick.
2. **Pounce**: when its head is within 40 art px of its prey, it starts running with ×1.35 acceleration. If it has not caught anything within 6 s, it resumes stalking.
3. **Capture**: when it touches a chicken, it grabs it and leaves with its prey toward the nearest edge (×2 speed). The chicken is "carried off for good" and replaced later.
4. The fox never rests or lies down while there is prey.

**If there are no chickens on the strip** (none are enabled, all have been carried off, or they are being held by the mouse): there is nothing to hunt, so the fox **explores the area**:
- Roams in random states (walking, running, standing, playing with a ball), turns around, and may run to the opposite corner or come back.
- Leaves through a **random** edge (not necessarily the nearest) after 12–30 s.
- **Lies down (`lie`) only if there is no dog on the strip.** If a dog appears while the fox is lying down, it gets up immediately.
- When a chicken appears on the strip, the fox abandons its walk and starts stalking.

**Looking ahead while carrying.** A fox running off (with prey or not) watches the way ahead like a dog does: if a dog is within 220 art px in front of it and no dog is nearer behind, it turns and runs to the other edge, prey in its teeth.

**Fleeing.** If a dog is within 120 art px (regardless of which way it is facing), the fox abandons its prey and runs away from the dog toward the edge on the opposite side.
If the dog catches and bites the fox, the fox does the same.

## 7. Dog

A dog does not eat or hunt anything: it is a **guard**, and its only role in the food chain is to chase foxes away. The rest of the time, it behaves like an ordinary pet (all random states, including `lie`).

**Detection.** A dog notices a fox in one of two ways:
- **Sight:** within 220 art px, on the side the dog is facing.
- **Hearing:** within 60 art px on either side, so a fox sneaking up from behind is heard. Every extra fox on the same side of the dog adds 60 art px: the more foxes sneak in from one corner, the louder the rustle and the farther it is heard.
- The dog is not in an "important" state. Whether it is walking, standing, or lying down does not matter: a lying dog gets up.

The reaction takes 100–700 ms. The fox can be in any state: hunting, roaming, or lying down.

**Chase.** The dog runs toward the fox and barks **intermittently**: a barking bout lasts 0.8–1.6 s, followed by 0.9–2.2 s of silent running, repeating in a loop. The first bout starts immediately when the fox is detected.
The chase ends if the fox is more than 220 art px away, 10 s have passed, or the dog touches it. A fox held by the mouse or in the air is not noticed and not chased.

**Barking** is the `bark` animation, a regular GIF like every other state (`<color>_bark_8fps.gif`, built from the first `idle` frame). The dog stands still during a bout. It is shown as a barely open mouth and puffs of air that leave the muzzle, spread out and thin away. One "woof" lasts 0.36 s (four frames of 90 ms): the mouth opens slightly, opens a little more, starts to close, then closes, while the puff moves away and fades. The tongue is not shown while barking. The bark canvas is wider than the idle one to fit the waves; the code compensates for the difference so the dog does not shift when it starts or stops barking.

**Bite.** On touching the fox, the dog lunges (`swipe`) once. The fox immediately drops its prey and runs away through the far edge; the chicken breaks free and panics, running away from the fox.

## 8. Snail and Clippy

Neutral pets. They only use random states and react to the mouse. They are not part of anyone's food chain, do not run away from anyone, and do not bother anyone.

## 9. What Happens Depending on Which Pets Are Enabled

| Enabled                    | What happens                                                                                            |
|----------------------------|---------------------------------------------------------------------------------------------------------|
| Chickens only              | Grass grows, chickens peck and lay eggs; eggs crack and evaporate                                       |
| Chickens + rats            | Same as above; rats eat broken eggs                                                                     |
| Chickens + foxes           | Foxes visit, stalk, and carry off chickens; carried-off chickens are replaced                           |
| Chickens + foxes + dogs    | Dogs chase foxes away while barking; when they catch one, they bite it and the fox releases the chicken |
| Foxes only (no chickens)   | Foxes visit, roam for 12–30 s, may lie down, leave through any edge, and then visit again               |
| Foxes + dogs (no chickens) | Foxes roam but do not lie down; a dog that sees or hears one chases it while barking and bites it    |
| Dogs only                  | No foxes and no barking. Dogs just roam, play, and lie down                                             |
| Dogs + chickens (no foxes) | Dogs do not eat or bother chickens; they walk nearby                                                    |
| Rats, snails, Clippy       | They are independent and do not affect or interact with anyone, except that rats eat eggs               |

## 10. Throwing and Bouncing off the Cursor

Applies to pets only (not eggs): after being thrown, a flying pet above the cursor bounces off the mouse cursor, and the bounces are counted. Code: `helpers/pets/bounce.py` (`BounceBehavior`, `CursorMotion`); the cursor is read every tick in `ui_pets.py`.

- **Board.** The obstacle is a pixel board centered on the cursor, drawn in the accent color of the theme (light top row with notched ends, darker bottom row) and snapped to its own pixel grid. It is the same for every pet: 2 cells thick, 1.25 times as wide as the widest pet on the strip, with cells as big as the biggest pet pixel (`CollisionBoard.for_pets`). The board exists only for a pet that was thrown (let go with a swing, not just put down) and only while that pet is above the board; a pet that is carried and lowered, dropped without a swing, or that has fallen below the cursor level, does not see it. What is drawn is exactly what collides. When the mouse picks up anything else (an egg, another pet) while a thrown pet is still in the air, that pet loses the board for the rest of its flight; it gets it back only after being thrown again. Flight is simulated in short slices (at most one board thickness of pet and cursor movement each), so a fast swing of the mouse cannot pass through the pet.
- **Direction.** The push is always up, tilted sideways by where the body is hit, like in Breakout: up to 0.6 of the push at the very end of the board, none in the middle. The speed of the cursor is added, so a flick hits harder.
- **Strength.** The pet gives back 90% of its approach speed. A hit always lifts the pet at least 1100 device px/s (about 250 px of height, 0.9 s in the air), enough time for a person to react and hit again. The total speed is capped at 2200 device px/s. 
- **One hit, one count.** After a hit, or right after the pet is released from the hand, the board cannot hit it again until the pet has got clear of the board.
- **Badge.** Every bounce adds 1 to a counter drawn centered above the pet with a 1 px gap (`999+` above 999). It has the same look as the counters on the buttons: `apply_counter_style` rendered into a pixmap by `counter_pixmap` in `components/badge.py`.
- **Miss.** When the pet lands on the floor, the badge stays for 2.5 s and then disappears, and the count resets. Picking the pet up from the floor before that starts a new attempt: the count and the badge are reset at once (and the chat fades back in). A pet caught in the air keeps its count, and the timer waits while it is held.
- **Fading the chat** (option "Fade the chat during throws": Off / Bounce / Flight, Off by default). A pet flying past lines of text can make them flicker before the eyes. **Bounce**: the chat fades out at the first bounce of a thrown pet off the board. **Flight**: it fades out as soon as any pet is thrown. In both modes the chat fades back in when every thrown pet has landed, not when the badge goes out (a miss brings it back at the landing). What fades is everything under the pets: the whole stack of screens (chat, chat logs, profile, tracker, pronunciation, banned users, settings); in a private room, the messages. The user list stays, the pets do not reach it. The messages keep arriving meanwhile; only the visibility changes. The fade-out time is the slider "Fade, ms" (250 ms by default, 50–1000); the return takes twice as long. It is one opacity effect on the widget (`components/fade.py`, `WidgetFader`) with a single animation, not a fade of every item; the effect exists only during the fade and while the content is hidden, a fully transparent widget is not drawn at all.

## 11. Settings

- A pet's icon in the settings is always in color. The number of enabled instances is shown by a badge in the corner (1 or more); with no badge, that pet is disabled.
- Left-click adds a pet, right-click removes one, and holding the button repeats the action. Maximum 10 of each color.
- Size is set for the entire species, in whole art pixels (×1…×10).
- Two sliders set the redraw rate of the strip: "Strip, fps" (pets on the ground, 30 by default) and "Flight, fps" (a pet or an egg held or in the air, 60 by default). The maximum is 165, or the refresh rate of the fastest screen when that is higher.
- A checkbox turns on fading the messages during a throw (off by default).
- The "i" button next to the hint opens a guide (English and Russian) describing the role and behavior of every pet.
- Changing the counts must stay cheap: decoded animations are kept in a bounded cache and are never cleared on a click, and existing pets are reused when the options are reloaded.

## 12. Resource Layout

Everything bundled lives in `ecosystem/` (located with `get_resource_dir("ecosystem")`):

```
ecosystem/
├── pets/
│   └── <species>/
│       ├── animations/   <color>_<state>_8fps.gif
│       └── icons/        icon_<color>.png
├── food/
│   └── <species>/
│       └── animations/   <color>_<state>_8fps.gif
└── pixel_grid.json
```

- The suffix of an icon or animation is always the color of the pet it shows.
- Food (`egg`, `grass`) has no icons: it is not shown in the settings.
- Who eats or guards against whom is not a matter of folders: it lives in `helpers/pets/relations.py`. Snails and Clippy sit in `pets/` like everyone else.
