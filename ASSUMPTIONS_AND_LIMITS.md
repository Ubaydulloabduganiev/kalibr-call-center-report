# Assumptions and limits

## Authentication

Version 1 does not ask employees for amoCRM passwords. An administrator synchronizes active amoCRM users, enables an access policy, and generates a one-time Telegram link. Every command re-verifies the linked amoCRM user through the Users API, cached for five minutes by default.

## Call counting

There is no telephony integration. A “call attempt” is therefore a configured amoCRM artifact:

- a completed task of one of the configured task type IDs;
- a note of one of the configured note types;
- or both, with source IDs preventing duplicates inside each adapter.

The system cannot prove that a physical call happened or lasted ten seconds unless amoCRM stores duration. Keep `minimum_duration_seconds=0` when duration is absent.

## Results

Success, failure and in-progress are configurable from:

- lead pipeline stage IDs;
- task-result text patterns;
- note parameter text patterns.

Current lead status is only a fallback. For historical precision, the result should be stored directly in the completed task or note, or webhooks should be enabled before the workflow starts.

## “New contact” metrics

The report separates:

- contacts created during the report period;
- contacts whose first imported call event falls in the report period.

The second metric is only as complete as the imported history. Increase `INITIAL_IMPORT_DAYS` before the first sync when older history matters.

## Access scopes

- Operator: own activity.
- Manager: same amoCRM group, unless explicit managed user IDs are configured.
- Executive: all active synchronized users.

Users are blocked by default until enabled by a bot administrator.
