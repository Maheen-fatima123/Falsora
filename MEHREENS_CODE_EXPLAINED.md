# What is Mehreen's Code? (The Decision Engine)

Before we merged everything together, Mehreen wrote a Python backend service to handle the "business logic" and "decision making" for the platform. We took her logic and packaged it into a standalone service called the **Decision Engine**.

Think of the system like a restaurant:
* **Node API (The Waiter):** Takes your order (the image), talks to the kitchen, and writes the final receipt (the database).
* **AI Engine (The Chef):** Does the heavy lifting of looking at the pixels and saying "this looks 99% fake."
* **Mehreen's Decision Engine (The Manager):** Looks at the Chef's score, looks at the metadata (like camera type), checks the rulebook, and makes the final executive decision on what to do with the case.

Here is exactly what her code does, broken down simply:

## 1. The Trust Score Calculator (`/trust-score`)
Instead of just relying purely on the AI to say if an image is real or fake, Mehreen's code calculates a composite **Trust Score**. It takes three things into account:
1. **The AI Score:** How fake does the neural network think this is?
2. **EXIF Flags:** Did the image metadata say it was edited in Photoshop? Was the metadata stripped out entirely?
3. **Fingerprint Match:** Have we seen this exact image before in our database?

Her code uses math to weigh all these factors together to give a final percentage score (e.g., 85% Trustworthy) and assigns a Risk Level (`Authentic`, `Uncertain`, or `High-Risk`).

## 2. The Live Stream Rolling Score (`/trust-score/rolling`)
When a user is verifying their identity via a live webcam stream (like a KYC check), we are analyzing 1 frame per second. Mehreen wrote a clever algorithm that calculates an "exponentially-weighted rolling average". 
* **What that means:** If the AI detects a deepfake glitch for just 1 second, it remembers it, but if the next 10 seconds are perfectly fine, the trust score slowly recovers. It prevents the system from failing a user just because their camera glitched for a split second, but catches them if they are consistently using a deepfake filter.

## 3. The State Machine Enforcer (`/case-status/validate`)
Cases in the system go through a strict lifecycle (e.g., `Analyzing` → `Flagged` or `Verified`).
Mehreen's code acts as the bouncer. If a bug in the code, or a malicious user, tries to change a case from `Verified` back to `Analyzing`, her code says "No, that's not allowed" and blocks the action. It ensures the investigation process follows the correct legal steps.

## 4. The Notification Formatter (`/notifications/format`)
When something happens (a case is flagged, a reviewer is assigned), the system needs to send an alert. Instead of hardcoding text everywhere, Mehreen's code holds the "templates" for all system alerts. It takes the case data and formats it into professional, human-readable notification text (e.g., *"Case CAS-142 has been Flagged for High-Risk activity."*).
