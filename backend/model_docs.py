"""Plain-language documentation for each projection model.

Every model in the picker gets three things here: a summary a non-statistician
can read, a short list of what the model actually looks at, and a link to a
neutral explanation of the technique so a curious user can go deeper without
taking our word for it.

For the trained model, `attends_to` is only the fallback - the API replaces it
with the model's measured feature importances for the stat being viewed, so the
UI reports what it learned to rely on rather than what we assumed it would.
"""

MODEL_DOCS: dict[str, dict] = {
    'ml': {
        'trained': True,
        'summary': (
            "A regression trained on eight seasons of real game logs. It learned, from "
            "roughly 34,000 past player-games, how much each signal below has actually "
            "mattered - nobody hand-picked the weights. Its uncertainty comes from the "
            "size of the errors it made on a season it was never trained on, so the "
            "probability reflects how wrong this model has genuinely been before."
        ),
        'attends_to': [
            'Recent form', 'Recent usage (targets, carries or attempts)',
            'Career baseline', "What the opposing defense gives up to the position",
        ],
        'url': 'https://en.wikipedia.org/wiki/Ridge_regression',
        'url_label': 'How ridge regression works',
    },
    'ensemble': {
        'summary': (
            "Blends two views: a textbook probability curve shaped to fit the stat, and "
            "the player's own game-by-game history. With only a few games to go on it "
            "leans on the curve, which is smoother; with a long history it leans on what "
            "the player has actually done. Weights are not learned - they are set by how "
            "much history exists."
        ),
        'attends_to': [
            "The player's last 10 games, recent ones weighted more heavily",
            'How much the opposing defense helps or hurts this stat',
            'How much history is available to trust',
        ],
        'url': 'https://en.wikipedia.org/wiki/Ensemble_learning',
        'url_label': 'What an ensemble is',
    },
    'lognormal': {
        'summary': (
            "Treats yardage the way yardage behaves: never negative, usually clustered "
            "low with a long tail of big games, and with a real chance of being held to "
            "zero. That lopsided shape is why a player's ceiling sits much further from "
            "their typical game than their floor does."
        ),
        'attends_to': [
            "The player's recent average", 'How much their yardage swings week to week',
            'How often they get shut out entirely',
        ],
        'url': 'https://en.wikipedia.org/wiki/Log-normal_distribution',
        'url_label': 'What a lognormal distribution is',
    },
    'negbin': {
        'summary': (
            "For things you count - receptions, carries, touchdowns. You cannot catch 4.3 "
            "passes, so this works in whole numbers. It also allows for the fact that "
            "usage swings a lot between games, which makes these stats more erratic than "
            "a simple counting model would predict."
        ),
        'attends_to': [
            'The average number of events per game',
            'How erratic that number is from week to week',
        ],
        'url': 'https://en.wikipedia.org/wiki/Negative_binomial_distribution',
        'url_label': 'What a negative binomial is',
    },
    'empirical': {
        'summary': (
            "Assumes no shape at all - it just uses the games the player has actually "
            "played, smoothed a little so a line falling between two past results still "
            "gets a sensible answer. This is the only model that can represent a player "
            "who is genuinely feast-or-famine rather than averaging out."
        ),
        'attends_to': [
            'Every one of the last 10 games, recent ones weighted more',
            'The actual spread of those results, not an assumed one',
        ],
        'url': 'https://en.wikipedia.org/wiki/Kernel_density_estimation',
        'url_label': 'What kernel smoothing is',
    },
    'triangular': {
        'summary': (
            "The original method, kept for comparison. It draws 10,000 random outcomes "
            "from a simple triangle fitted to the best, worst and average of the player's "
            "last three games. Because the triangle stops at their best and worst game, "
            "it reports 0% for any line beyond that range - which is why it is no longer "
            "the default."
        ),
        'attends_to': [
            'Only the last three games', 'Their minimum, average and maximum',
        ],
        'url': 'https://en.wikipedia.org/wiki/Monte_Carlo_method',
        'url_label': 'What Monte Carlo simulation is',
    },
}
