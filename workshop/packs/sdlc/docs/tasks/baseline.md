# 1. Feel the pain first

Stay in Continue **Chat** mode. Do not provide logs, tickets, or previous chat
history.

Ask:

> A messaging gateway submit timed out downstream and the customer received
> the message twice. What exact prior incident explains this? Give me the
> ticket ID, status, root cause, and approved mitigation. Do not guess.

Notice what today's context-free assistant cannot do:

- It can produce polished retry advice, but cannot cite your incident.
- You must find and paste operational context yourself.
- It cannot distinguish an approved mitigation from a plausible suggestion.

Now choose **New Session** and ask:

> What mitigation did our team approve for that duplicate-delivery incident?

The answer is gone with the chat. Your assistant has amnesia, your incident
system is somewhere else, and another engineer will repeat the same search.

[Repeat the job with Iris →](/tasks/iris-workflow.md)
