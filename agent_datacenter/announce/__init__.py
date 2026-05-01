"""
agent_datacenter.announce — capability announce protocol (v1).

An agent plugs in by sending an IdentityEnvelope to comms://announce.
The AnnounceBroker resolves the agent's profile, assembles a Manifest,
and replies on the agent's primary mailbox.
"""
