import pandas as pd

from app.intent.recognizer import IntentRecognizer


recognizer = IntentRecognizer(
    "data/intents.csv"
)


clear_data = pd.read_csv(
    "data/validation.csv"
)

ambiguous_data = pd.read_csv(
    "data/ambiguous.csv"
)

unknown_data = pd.read_csv(
    "data/unknown.csv"
)


# --------------------------------------------------
# Collect raw scores
# --------------------------------------------------

def get_result(sentence):

    return recognizer.predict(sentence)


clear_results = [
    get_result(sentence)
    for sentence in clear_data["sentence"]
]


ambiguous_results = [
    get_result(sentence)
    for sentence in ambiguous_data["sentence"]
]


unknown_results = [
    get_result(sentence)
    for sentence in unknown_data["sentence"]
]


# --------------------------------------------------
# Threshold evaluation
# --------------------------------------------------

similarity_thresholds = [
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75
]


margin_thresholds = [
    0.05,
    0.10,
    0.15,
    0.20
]


print("\n" + "=" * 90)
print("THRESHOLD EXPERIMENT")
print("=" * 90)


for similarity_threshold in similarity_thresholds:

    for margin_threshold in margin_thresholds:

        clear_accepted = 0

        ambiguous_rejected = 0

        unknown_rejected = 0

        # ------------------------------------------
        # Clear intent acceptance
        # ------------------------------------------

        for result in clear_results:

            score = result["similarity_score"]
            margin = result["margin"]

            if (
                score >= similarity_threshold
                and
                margin >= margin_threshold
            ):
                clear_accepted += 1


        # ------------------------------------------
        # Ambiguous rejection
        # ------------------------------------------

        for result in ambiguous_results:

            score = result["similarity_score"]
            margin = result["margin"]

            accepted = (
                score >= similarity_threshold
                and
                margin >= margin_threshold
            )

            if not accepted:
                ambiguous_rejected += 1


        # ------------------------------------------
        # Unknown rejection
        # ------------------------------------------

        for result in unknown_results:

            score = result["similarity_score"]
            margin = result["margin"]

            accepted = (
                score >= similarity_threshold
                and
                margin >= margin_threshold
            )

            if not accepted:
                unknown_rejected += 1


        clear_rate = (
            clear_accepted
            / len(clear_results)
        )

        ambiguous_rate = (
            ambiguous_rejected
            / len(ambiguous_results)
        )

        unknown_rate = (
            unknown_rejected
            / len(unknown_results)
        )


        print(
            f"\nSimilarity={similarity_threshold:.2f} "
            f"Margin={margin_threshold:.2f}"
        )

        print(
            f"Clear accepted: "
            f"{clear_accepted}/{len(clear_results)} "
            f"({clear_rate:.2%})"
        )

        print(
            f"Ambiguous rejected: "
            f"{ambiguous_rejected}/{len(ambiguous_results)} "
            f"({ambiguous_rate:.2%})"
        )

        print(
            f"Unknown rejected: "
            f"{unknown_rejected}/{len(unknown_results)} "
            f"({unknown_rate:.2%})"
        )