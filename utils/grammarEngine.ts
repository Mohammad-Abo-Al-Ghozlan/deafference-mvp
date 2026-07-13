/**
 * Grammar Reordering Module Scaffold
 *
 * Sits immediately after the Gloss Buffer & Debounce layer (KAN-23 / useGlossBuffer).
 * Once KAN-23 finalizes a stabilized array of gloss words (e.g. ["STORE", "I", "GO"]),
 * this module is responsible for reordering/translating them into a grammatically
 * correct English sentence (e.g. "I am going to the store.").
 *
 * Currently a pass-through stub: it does no reordering, just joins the glosses with
 * spaces. This keeps the existing UI rendering lifecycle unchanged while giving every
 * downstream consumer a stable interface to code against ahead of the real engine.
 */

/** Strict input contract: a stabilized array of gloss words, in recognition order */
export interface GrammarReorderInput {
  glosses: string[];
}

/** Strict output contract: the resulting sentence, ready to render or speak */
export interface GrammarReorderOutput {
  orderedSentence: string;
}

/**
 * Reorders a stabilized gloss sequence into a sentence.
 *
 * @param input.glosses - Finalized gloss words from the buffer/debounce layer, e.g. ["STORE", "I", "GO"]
 * @returns The sentence to display, e.g. "STORE I GO" (pass-through) or, once the real
 *          engine is in place, "I am going to the store."
 */
export function reorderGlosses({ glosses }: GrammarReorderInput): GrammarReorderOutput {
  // --- PASS-THROUGH STUB (current behavior) ---
  // No grammar transformation yet: just space-join the glosses in recognition order.
  const orderedSentence = glosses.join(' ');

  // --- FUTURE INTEGRATION POINT ---
  // Replace the line above with the real reordering call once it exists, e.g.:
  //
  //   const orderedSentence = await callGrammarLLM(glosses);
  //     - POST glosses to an LLM/NLP endpoint (e.g. a fine-tuned seq2seq or GPT-style
  //       prompt: "Convert these ASL glosses to fluent English: ...") and use its
  //       response as orderedSentence.
  //
  //   const orderedSentence = applyTranslationMatrix(glosses);
  //     - Run glosses through a rule-based ASL-to-English grammar matrix (handling
  //       topicalization, time markers, classifiers, non-manual grammar cues, etc.)
  //       before falling back to the LLM path above for anything the matrix can't cover.
  //
  // Note: reorderGlosses will need to become async (Promise<GrammarReorderOutput>) to
  // support either of the above, since both involve a network/inference call.

  return { orderedSentence };
}
