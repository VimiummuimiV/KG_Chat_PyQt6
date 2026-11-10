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
- **Strip edges**: a pet turns around when it reaches an edge.
- **Mouse**: clicking a pet triggers panic (runs for 1.2–2.2 s and forgets everything); click and drag to throw it—it flies and panics on landing. Eggs can be picked up and rolled; grass cannot be picked up.
- **"Important" state**: panic, being held by the mouse, and flight. In these states, a pet notices nothing and does not react to anything.

## 3. Chicken

- Pecks at grass by running up to the nearest clump (reaction delay: 150–1500 ms). One clump = 4 pecks = one egg.
- Lays eggs while walking: once every 20–50 s of walking, if it has enough food for at least one egg (it starts with enough for one).
- To lay, the hen stops and sits down (`lay` animation, 1.6 s, played once). The egg leaves her tail at 40% of the animation, then she stands up and walks on in the same direction. While she runs for food or panics, laying waits; a scare or a fox interrupts it, and then no food is spent.
- If a fox is hunting and comes within 70 art px, the chicken runs away from it for 2–3.5 s.
- It will not run for food past a fox: if a fox is in the way, the chicken gives up on the food.
- If another pet is clearly going to reach the food first (by at least 0.5 s), the chicken stops and watches.
- A chicken carried off by a fox is replaced after half the average interval between predator visits. The new chicken enters from the edge farthest from the foxes, or, if there are no foxes, from the opposite edge to the one the previous chicken was carried off through.

## 4. Grass and Eggs

**Grass** grows only while there is at least one chicken. There are no more than 2 clumps per chicken. A new clump appears every 10–25 s (the more chickens, the more frequently). Eaten clumps disappear; when the last chicken disappears, all the grass is removed.

**Eggs** fall from a chicken's tail (drawn behind the pets, so a laid egg lies behind its hen) and roll according to the shape of the strip. They break on a hard landing (being thrown or falling from a height of about 75 px). An intact egg remains for up to 90 s, then cracks on its own once it is almost motionless. A broken egg remains for 8 s (time spent being eaten does not count), then evaporates. Only pets with the `eat` animation—that is, rats—can eat eggs, and only when they are broken. If there are no rats, eggs simply crack and evaporate.

## 5. Rat

- Runs to a broken egg and eats it from the edges, taking a quarter per bite.
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
The chase ends if the fox is more than 220 art px away, 10 s have passed, or the dog touches it.

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

## 10. Settings

- A pet's icon in the settings is always in color. The number of enabled instances is shown by a badge in the corner (1 or more); with no badge, that pet is disabled.
- Left-click adds a pet, right-click removes one, and holding the button repeats the action. Maximum 10 of each color.
- Size is set for the entire species, in whole art pixels (×1…×10).
- The "i" button next to the hint opens a guide (English and Russian) describing the role and behavior of every pet.
- Changing the counts must stay cheap: decoded animations are kept in a bounded cache and are never cleared on a click, and existing pets are reused when the options are reloaded.

## 11. Resource Layout

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

## 12. Not Connected

`helpers/pets/options.py` (`HuntingOptions`: raid interval, capture chance) is currently not imported anywhere and does not affect behavior. The "Predator visits every" slider is read from `helpers/pets/catalog.py`.
