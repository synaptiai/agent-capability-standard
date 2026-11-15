/**
 * One thread's record keeping, one piece at a time.
 *
 * The thread's key-value store has no conditional write, so a check and the
 * write that acts on it (an approval read as unused, then marked used) are
 * two steps. The Standard Agent Specification runs one execution of a thread
 * at a time ("A single thread MUST NOT execute multiple concurrent flows",
 * Runtime §11), but nothing stops a tool's own code from starting two calls
 * through `state.invokeTool()` without waiting for the first. A queue per
 * thread in this module makes each check-and-write step whole for the calls
 * that run in this JavaScript realm. The specification does not say where an
 * invoked tool runs, so two such calls are serialised here only where the
 * runtime runs them in one realm.
 *
 * Code outside an execution, such as a thread endpoint, may run at the same
 * moment as an execution and in another realm. The binding therefore refuses
 * a call that needs an approval or a checkpoint there (see `groundedTool`).
 */

const queues = new Map<string, Promise<void>>();

/** Run `work` once every piece of work queued earlier under `key` has settled. */
export async function serially<T>(key: string, work: () => Promise<T>): Promise<T> {
  const previous = queues.get(key) ?? Promise.resolve();
  const run = previous.then(work);
  const settled = run.then(
    () => undefined,
    () => undefined,
  );
  queues.set(key, settled);
  try {
    return await run;
  } finally {
    if (queues.get(key) === settled) queues.delete(key);
  }
}
