+++
title = "Federations"
children = ["federation-users", "federation-admin", "federation-owner"]
+++

# Federations

Manage several groups? A federation lets them share bans, so you can keep a banned user out of every group that joins it.

Use the guides below to check bans, moderate members, or create and manage a federation.

Ask the federation owner for its ID. If your group already belongs to it, `/chatfed` shows the ID.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Group admin commands:**

- `/chatfed`: View the group's federation.
- `/quietfed`: Toggle federation ban messages in this group.

**Group owner commands:**

- `/joinfed <federation_id>`: Join a federation.
- `/leavefed`: Leave the group's federation.

**Examples:**

- Join using the federation's ID:\
  `/joinfed 12345678-1234-1234-1234-123456789abc`
- Check which federation the group belongs to:\
  `/chatfed`
