# Contributing

This is a community project. Pull requests are open to anyone, agent or human, on anything that builds it out or checks it.

## The rule that comes from the proposal itself

> A test nobody can fail is not the test the brief asked for.

That holds for the code as much as for the fly. A null that cannot fire is not a null. A test that passes whether or not the behaviour exists is not a test. If you add a guard, say in the pull request what mutation kills it: delete the behaviour in a scratch copy, watch it go red, and name that.

## What gets merged

- **Seal before you score.** A battery change is a new sealed version. Earlier versions stay published as sealed and scored, and a run says which version it was scored against.
- **Runs publish their inputs.** Seeds, substrate hash, battery hash and simulator version go in every row, so a stranger recomputes rather than trusts.
- **Reusable over one-off.** The substrate loader, the two nulls, the encoders, the decoders and the battery predicates are library code with an interface, not cells in a results notebook. A result that cannot be re-run by the next build does not count as done.
- **The author of a battery does not score their own simulator against it.** Scoring is done by a seat with no stake in the simulator passing.
- **Downgrades are published.** A result that narrows is stated in the README beside the old one, not in place of it.

## What this project will not do

- Redistribute the connectome. Fetch it from its publisher and check the hash.
- Let a language model make the decision the connectome is supposed to make.
- Call a result on a wiring diagram a living brain.

## Scope

Off-theme is fine to propose, but the bar for merging is whether it helps something in the README get built or checked. Nobody is staffed to reply on a schedule; an unanswered pull request means unanswered, not rejected.

## Licence

Code MIT; battery definitions and results CC BY 4.0. By opening a pull request you agree your contribution ships under those terms.
