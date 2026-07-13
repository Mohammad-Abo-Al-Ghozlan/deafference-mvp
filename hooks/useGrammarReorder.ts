'use client';

import { useMemo } from 'react';
import { reorderGlosses, GrammarReorderOutput } from '@/utils/grammarEngine';

/**
 * React binding over the Grammar Reordering Module scaffold (see utils/grammarEngine.ts
 * for the pass-through stub logic and the future LLM/translation-matrix injection point).
 *
 * Recomputes only when the stabilized gloss array actually changes, so it's safe to call
 * on every render of a component that displays `glossBufferState.stabilizedSentence`.
 *
 * @param glosses - Finalized gloss words from the KAN-23 gloss buffer/debounce layer
 * @returns The current orderedSentence (pass-through today; grammar-corrected once
 *          the real engine replaces the stub)
 *
 * @example
 * const { orderedSentence } = useGrammarReorder(glossBufferState.stabilizedSentence);
 */
export const useGrammarReorder = (glosses: string[]): GrammarReorderOutput => {
  return useMemo(() => reorderGlosses({ glosses }), [glosses]);
};

export default useGrammarReorder;
