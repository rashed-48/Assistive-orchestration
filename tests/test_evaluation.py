import pandas as pd

from app.intent.recognizer import IntentRecognizer

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)


recognizer = IntentRecognizer(
    "data/intents.csv"
)


validation = pd.read_csv(
    "data/validation.csv"
)


y_true = []
y_pred = []

accepted_count = 0
rejected_count = 0


for _, row in validation.iterrows():

    result = recognizer.predict(
        row["sentence"]
    )

    y_true.append(row["intent"])

    # Only count an intent prediction
    # when the decision layer accepts it.
    if result["decision"] == "PREDICTED":

        y_pred.append(result["intent"])
        accepted_count += 1

    else:

        y_pred.append("REJECTED")
        rejected_count += 1


print("\n" + "=" * 70)
print("CLEAR INTENT VALIDATION")
print("=" * 70)


print(
    f"\nTotal samples: {len(validation)}"
)

print(
    f"Accepted: {accepted_count}"
)

print(
    f"Rejected: {rejected_count}"
)


# --------------------------------------------------
# Overall decision acceptance
# --------------------------------------------------

acceptance_rate = (
    accepted_count / len(validation)
)


print(
    f"\nClear Intent Acceptance Rate: "
    f"{acceptance_rate:.4f}"
)


# --------------------------------------------------
# Intent classification
# --------------------------------------------------

labels = sorted(
    validation["intent"].unique()
)


print("\nClassification Report:\n")

print(
    classification_report(
        y_true,
        y_pred,
        labels=labels + ["REJECTED"],
        zero_division=0
    )
)


# --------------------------------------------------
# Confusion Matrix
# --------------------------------------------------

print("\nConfusion Matrix:\n")

matrix = confusion_matrix(
    y_true,
    y_pred,
    labels=labels + ["REJECTED"]
)


print(
    "Labels:"
)

print(
    labels + ["REJECTED"]
)

print()

print(matrix)