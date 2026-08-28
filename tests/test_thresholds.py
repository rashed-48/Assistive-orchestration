"""Similarity-threshold sweep for the intent recognizer.

Run with:

    python -m tests.test_thresholds

This script chooses the single similarity threshold that separates supported
commands from unsupported input. It reports, for each candidate threshold:

    validation.csv  how many clear commands are still predicted
    ambiguous.csv   how many deliberately vague phrases fall below threshold
    unknown.csv     how many out-of-scope requests fall below threshold

This sweep used to have a second dimension: a "margin" gate that also
required a minimum gap between the best and second-best intent. That gate was
retired. It refused to predict a command whenever another intent scored
close, which rejected core commands - "I want to sleep" clears the similarity
threshold comfortably at 0.89 but has only a 0.193 gap over WAKE_UP. The
system now always predicts the best supported intent and asks the user to
confirm it, so the only threshold left to tune is similarity.

Phrases in ambiguous.csv are therefore no longer expected to be rejected.
They are reported to show what a given threshold does to vague input; the
confirmation step, not a score gate, is what protects the user.
"""

import pandas as pd

from app.intent.recognizer import IntentRecognizer


SIMILARITY_THRESHOLDS = [
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
]


def main():

    recognizer = IntentRecognizer(
        "data/intents.csv"
    )

    # --------------------------------------------------
    # Collect raw scores once
    # --------------------------------------------------

    def score_dataset(name):

        data = pd.read_csv(
            f"data/{name}.csv"
        )

        return [
            recognizer.predict(sentence)
            for sentence in data["sentence"].dropna()
        ]

    clear_results = score_dataset("validation")

    ambiguous_results = score_dataset("ambiguous")

    unknown_results = score_dataset("unknown")

    # --------------------------------------------------
    # Threshold evaluation
    # --------------------------------------------------

    print("\n" + "=" * 90)
    print("SIMILARITY THRESHOLD EXPERIMENT")
    print("=" * 90)

    def count_above(results, threshold):

        return sum(
            1
            for result in results
            if result["similarity_score"] >= threshold
        )

    for threshold in SIMILARITY_THRESHOLDS:

        clear_predicted = count_above(
            clear_results,
            threshold
        )

        ambiguous_rejected = (
            len(ambiguous_results)
            - count_above(ambiguous_results, threshold)
        )

        unknown_rejected = (
            len(unknown_results)
            - count_above(unknown_results, threshold)
        )

        print(
            f"\nSimilarity={threshold:.2f}"
        )

        print(
            f"Clear predicted: "
            f"{clear_predicted}/{len(clear_results)} "
            f"({clear_predicted / len(clear_results):.2%})"
        )

        print(
            f"Ambiguous below threshold: "
            f"{ambiguous_rejected}/{len(ambiguous_results)} "
            f"({ambiguous_rejected / len(ambiguous_results):.2%})"
        )

        print(
            f"Unknown below threshold: "
            f"{unknown_rejected}/{len(unknown_results)} "
            f"({unknown_rejected / len(unknown_results):.2%})"
        )


if __name__ == "__main__":
    main()
