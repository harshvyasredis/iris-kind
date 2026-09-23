# Build an agent the gateway can afford

The messaging gateway already sees both sides: what brands send, what recipients
reply, what was delivered, and what was blocked. You will build with simulated
versions of that data—no brand system or new integration.

In 90 minutes you will:

1. retrieve one useful 2023 incident instead of stuffing twenty tickets into a prompt;
2. remember a reply that arrives two days later and catch an opt-out that is not `STOP`;
3. reuse answers without returning one brand's identity to another;
4. compete with the naive agent on accuracy, prompt tokens, latency, and peak context.

You write JavaScript in **Code** and run it in **App**. YAML files record the
schema and policy decisions behind that code.

This is fictional, representative carrier messaging data—not Verizon production
data or architecture. The result is a human-reviewed copilot, not an autonomous
gateway control plane.

[Set up and establish the baseline →](/setup/setup.md)
