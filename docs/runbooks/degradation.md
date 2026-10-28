# When the reviewer is unreachable

The system notices after 72 hours without a decision from the primary reviewer and flips the tenant to degraded. What changes and what does not:

**Keeps flowing.** Answers already approved on unchanged, fresh claims, under the ladder's rules (level 2 only for approved customers). Nothing else.

**Held.** Every novel, changed, contractual or flagged question. Never auto-shipped, never at a lower bar.

**Said out loud.** The account executive gets a dated status per deal: how many held, the oldest, and that review is paused. The degradation banner says the same inside the app.

**Escalated.** Deal-blocking questions go to the named backup with a one-page list: the question, its class, its route, its age. The backup can approve from the queue like the primary.

**When the reviewer returns.** The queue is waiting, ranked. The banner clears on their first decision.

Set the names before you need them:

```
POST /v1/degradation/backup  {"primary_reviewer": "<email>", "backup_reviewer": "<email>", "ladder_level": 1}
```

What this is not: a workaround. The design holds the same bar with one person missing, which is what the challenge round asked for.
