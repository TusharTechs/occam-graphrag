window.OCCAM_DATA = {
 "n": 100,
 "metrics": {
  "rag": {
   "acc": 0.63,
   "tokQ": 3259.32,
   "tokCorrect": 5173.523809523809,
   "recall": 0.756092
  },
  "graphrag": {
   "acc": 0.97,
   "tokQ": 838.17,
   "tokCorrect": 864.0927835051547,
   "recall": 0.979737
  },
  "agentic": {
   "acc": 1.0,
   "tokQ": 890.38,
   "tokCorrect": 890.38,
   "recall": 0.989737
  },
  "occam": {
   "acc": 1.0,
   "tokQ": 64.24,
   "tokCorrect": 64.24,
   "recall": 0.994737
  }
 },
 "byType": {
  "aggregation": {
   "rag": 0.09523809523809523,
   "graphrag": 1.0,
   "agentic": 1.0,
   "occam": 1.0,
   "n": 21
  },
  "temporal": {
   "rag": 0.6818181818181818,
   "graphrag": 0.9090909090909091,
   "agentic": 1.0,
   "occam": 1.0,
   "n": 22
  },
  "superlative": {
   "rag": 0.6,
   "graphrag": 1.0,
   "agentic": 1.0,
   "occam": 1.0,
   "n": 10
  },
  "multi_hop": {
   "rag": 0.75,
   "graphrag": 0.9642857142857143,
   "agentic": 1.0,
   "occam": 1.0,
   "n": 28
  },
  "lookup": {
   "rag": 1.0,
   "graphrag": 1.0,
   "agentic": 1.0,
   "occam": 1.0,
   "n": 19
  }
 },
 "tiers": [
  {
   "tier": "tier0_rule_graph",
   "n": 98,
   "tokQ": 0.0
  },
  {
   "tier": "tier1_disambiguated",
   "n": 1,
   "tokQ": 263.0
  },
  {
   "tier": "tier3_document_fallback",
   "n": 1,
   "tokQ": 6161.0
  }
 ],
 "questions": [
  {
   "qid": "pub-001",
   "question": "According to the provided corpus, how many biathlon events at the 2018 Winter Olympics had more than 73 competitors?",
   "qtype": "aggregation",
   "gold": "5",
   "goldDocs": 11,
   "runs": {
    "rag": {
     "answer": null,
     "correct": false,
     "tokens": 3890,
     "latency": 2.518,
     "tier": "rag",
     "stop": "model reported insufficient evidence",
     "recall": 0.5455,
     "docs": 10,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.129,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 3890,
       "latency": 2.388,
       "outcome": "insufficient"
      }
     ]
    },
    "graphrag": {
     "answer": "5",
     "correct": true,
     "tokens": 837,
     "latency": 2.113,
     "tier": "graphrag",
     "stop": "single graph query satisfied the question",
     "recall": 1.0,
     "docs": 11,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=count_above",
       "tokens": 837,
       "latency": 2.113,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "plan={'intent': 'count_above', 'sport': 'Biathlon', 'games_year': 2018, 'games_season': 'Winter', 'field_name': 'competitors', 'threshold': 73, 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "agentic": {
     "answer": "5",
     "correct": true,
     "tokens": 837,
     "latency": 1.904,
     "tier": "agentic",
     "stop": "evidence sufficient on first plan",
     "recall": 1.0,
     "docs": 11,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=count_above",
       "tokens": 837,
       "latency": 1.904,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "iteration 1: count_above",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "5",
     "correct": true,
     "tokens": 0,
     "latency": 0.0,
     "tier": "tier0_rule_graph",
     "stop": "answered at tier 0 with no LLM call",
     "recall": 1.0,
     "docs": 11,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:count_above",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "tier 0: count_above",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    }
   }
  },
  {
   "qid": "pub-055",
   "question": "Who won the gold medal in the men's 80 kg taekwondo event at the Summer Olympics held immediately before 2016?",
   "qtype": "temporal",
   "gold": "Sebasti\u00e1n Crismanich",
   "goldDocs": 2,
   "runs": {
    "rag": {
     "answer": null,
     "correct": false,
     "tokens": 3769,
     "latency": 1.904,
     "tier": "rag",
     "stop": "model reported insufficient evidence",
     "recall": 0.5,
     "docs": 7,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.111,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 3769,
       "latency": 1.793,
       "outcome": "insufficient"
      }
     ]
    },
    "graphrag": {
     "answer": null,
     "correct": false,
     "tokens": 848,
     "latency": 1.739,
     "tier": "graphrag",
     "stop": "stopped without escalating: ambiguous_discipline: 3 candidates in 2012",
     "recall": 0.0,
     "docs": 0,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=prev_edition",
       "tokens": 848,
       "latency": 1.739,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "plan={'intent': 'prev_edition', 'sport': 'Taekwondo', 'games_year': 2016, 'games_season': 'Summer', 'gender': 'men', 'discipline': '80 kg', 'field_name': 'competitors', 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ambiguous"
      }
     ]
    },
    "agentic": {
     "answer": "Sebasti\u00e1n Crismanich",
     "correct": true,
     "tokens": 1117,
     "latency": 3.471,
     "tier": "agentic",
     "stop": "resolved ambiguity with a constraint from the question",
     "recall": 0.5,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=prev_edition",
       "tokens": 848,
       "latency": 2.14,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "iteration 1: prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ambiguous"
      },
      {
       "agent": "disambiguator",
       "action": "llm_disambiguate",
       "detail": "3 candidates: ambiguous_discipline: 3 candidates in 2012 -> chose \"Taekwondo at the 2012 Summer Olympics \u2013 Men's 80 kg\"",
       "tokens": 269,
       "latency": 1.33,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "Sebasti\u00e1n Crismanich",
     "correct": true,
     "tokens": 263,
     "latency": 1.806,
     "tier": "tier1_disambiguated",
     "stop": "resolved a tier 0 ambiguity without re-planning",
     "recall": 0.5,
     "docs": 1,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "tier 0: prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ambiguous"
      },
      {
       "agent": "disambiguator",
       "action": "llm_disambiguate",
       "detail": "3 candidates: ambiguous_discipline: 3 candidates in 2012 -> chose \"Taekwondo at the 2012 Summer Olympics \u2013 Men's 80 kg\"",
       "tokens": 263,
       "latency": 1.805,
       "outcome": "ok"
      }
     ]
    }
   }
  },
  {
   "qid": "pub-040",
   "question": "Who won the gold medal in the individual normal hill/10 km nordic combined event at the Winter Olympics held immediately before 2014?",
   "qtype": "temporal",
   "gold": "Jason Lamy Chappuis",
   "goldDocs": 2,
   "runs": {
    "rag": {
     "answer": "Jason Lamy Chappuis",
     "correct": true,
     "tokens": 3557,
     "latency": 3.074,
     "tier": "rag",
     "stop": "single retrieval pass complete",
     "recall": 1.0,
     "docs": 6,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.125,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 3557,
       "latency": 2.949,
       "outcome": "ok"
      }
     ]
    },
    "graphrag": {
     "answer": null,
     "correct": false,
     "tokens": 853,
     "latency": 1.458,
     "tier": "graphrag",
     "stop": "stopped without escalating: ambiguous_discipline: 0 candidates in 2010",
     "recall": 0.0,
     "docs": 0,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=prev_edition",
       "tokens": 853,
       "latency": 1.457,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "plan={'intent': 'prev_edition', 'sport': 'Nordic combined', 'games_year': 2014, 'games_season': 'Winter', 'gender': 'men', 'discipline': 'Individual normal hill/10 km', 'field_name': 'competitors', 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "insufficient"
      }
     ]
    },
    "agentic": {
     "answer": "Jason Lamy Chappuis",
     "correct": true,
     "tokens": 1731,
     "latency": 4.378,
     "tier": "agentic",
     "stop": "evidence sufficient after 2 iteration(s)",
     "recall": 0.5,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=prev_edition",
       "tokens": 853,
       "latency": 1.609,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "iteration 1: prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "insufficient"
      },
      {
       "agent": "orchestrator",
       "action": "llm_plan",
       "detail": "intent=field_of_event (after: ambiguous_discipline: 0 candidates in 2010)",
       "tokens": 878,
       "latency": 2.769,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_vertex_lookup",
       "detail": "iteration 2: field_of_event",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "Jason Lamy Chappuis",
     "correct": true,
     "tokens": 0,
     "latency": 0.0,
     "tier": "tier0_rule_graph",
     "stop": "answered at tier 0 with no LLM call",
     "recall": 1.0,
     "docs": 2,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_prev_edition",
       "detail": "tier 0: prev_edition",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    }
   }
  },
  {
   "qid": "pub-004",
   "question": "According to the provided corpus, which athletics event at the 2008 Summer Olympics had the highest number of competitors?",
   "qtype": "superlative",
   "gold": "Athletics at the 2008 Summer Olympics \u2013 Men's marathon",
   "goldDocs": 43,
   "runs": {
    "rag": {
     "answer": "Ath",
     "correct": false,
     "tokens": 4037,
     "latency": 1.882,
     "tier": "rag",
     "stop": "single retrieval pass complete",
     "recall": 0.1628,
     "docs": 10,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.104,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 4037,
       "latency": 1.778,
       "outcome": "ok"
      }
     ]
    },
    "graphrag": {
     "answer": "Athletics at the 2008 Summer Olympics \u2013 Men's marathon",
     "correct": true,
     "tokens": 825,
     "latency": 2.451,
     "tier": "graphrag",
     "stop": "single graph query satisfied the question",
     "recall": 1.0,
     "docs": 43,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=argmax",
       "tokens": 825,
       "latency": 2.451,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "plan={'intent': 'argmax', 'sport': 'Athletics', 'games_year': 2008, 'games_season': 'Summer', 'field_name': 'competitors', 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "agentic": {
     "answer": "Athletics at the 2008 Summer Olympics \u2013 Men's marathon",
     "correct": true,
     "tokens": 825,
     "latency": 2.875,
     "tier": "agentic",
     "stop": "evidence sufficient on first plan",
     "recall": 1.0,
     "docs": 43,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=argmax",
       "tokens": 825,
       "latency": 2.875,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "iteration 1: argmax",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "Athletics at the 2008 Summer Olympics \u2013 Men's marathon",
     "correct": true,
     "tokens": 0,
     "latency": 0.0,
     "tier": "tier0_rule_graph",
     "stop": "answered at tier 0 with no LLM call",
     "recall": 1.0,
     "docs": 43,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:argmax",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_aggregation",
       "detail": "tier 0: argmax",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    }
   }
  },
  {
   "qid": "pub-005",
   "question": "Who won the gold medal in the event held at Olympic Weightlifting Gymnasium on 20 September 1988?",
   "qtype": "multi_hop",
   "gold": "Naim S\u00fcleymano\u011flu",
   "goldDocs": 1,
   "runs": {
    "rag": {
     "answer": "Naim S\u00fcleymano\u011flu",
     "correct": true,
     "tokens": 2698,
     "latency": 2.116,
     "tier": "rag",
     "stop": "single retrieval pass complete",
     "recall": 1.0,
     "docs": 9,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.1,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 2698,
       "latency": 2.016,
       "outcome": "ok"
      }
     ]
    },
    "graphrag": {
     "answer": "Naim S\u00fcleymano\u011flu",
     "correct": true,
     "tokens": 842,
     "latency": 3.309,
     "tier": "graphrag",
     "stop": "single graph query satisfied the question",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=venue_date",
       "tokens": 842,
       "latency": 3.309,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_venue_date",
       "detail": "plan={'intent': 'venue_date', 'games_year': 1988, 'games_season': 'Summer', 'venue': 'Olympic Weightlifting Gymnasium', 'date': '20 September 1988', 'field_name': 'competitors', 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "agentic": {
     "answer": "Naim S\u00fcleymano\u011flu",
     "correct": true,
     "tokens": 842,
     "latency": 2.33,
     "tier": "agentic",
     "stop": "evidence sufficient on first plan",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=venue_date",
       "tokens": 842,
       "latency": 2.33,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_venue_date",
       "detail": "iteration 1: venue_date",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "Naim S\u00fcleymano\u011flu",
     "correct": true,
     "tokens": 0,
     "latency": 0.0,
     "tier": "tier0_rule_graph",
     "stop": "answered at tier 0 with no LLM call",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:venue_date",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_traversal_venue_date",
       "detail": "tier 0: venue_date",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    }
   }
  },
  {
   "qid": "pub-009",
   "question": "How many nations competed in Sailing at the 2016 Summer Olympics \u2013 Women's RS:X?",
   "qtype": "lookup",
   "gold": "26",
   "goldDocs": 1,
   "runs": {
    "rag": {
     "answer": "26",
     "correct": true,
     "tokens": 2591,
     "latency": 2.355,
     "tier": "rag",
     "stop": "single retrieval pass complete",
     "recall": 1.0,
     "docs": 6,
     "steps": [
      {
       "agent": "retriever",
       "action": "vector_similarity_search",
       "detail": "top-10 hybrid (dense+bm25)",
       "tokens": 0,
       "latency": 0.086,
       "outcome": "ok"
      },
      {
       "agent": "reader",
       "action": "llm_read",
       "detail": "10 chunks in context",
       "tokens": 2591,
       "latency": 2.269,
       "outcome": "ok"
      }
     ]
    },
    "graphrag": {
     "answer": "26",
     "correct": true,
     "tokens": 819,
     "latency": 1.501,
     "tier": "graphrag",
     "stop": "single graph query satisfied the question",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=field_of_event",
       "tokens": 819,
       "latency": 1.501,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_vertex_lookup",
       "detail": "plan={'intent': 'field_of_event', 'title': \"Sailing at the 2016 Summer Olympics \u2013 Women's RS:X\", 'field_name': 'nations', 'answer_field': 'gold', 'note': 'llm'}",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "agentic": {
     "answer": "26",
     "correct": true,
     "tokens": 819,
     "latency": 2.319,
     "tier": "agentic",
     "stop": "evidence sufficient on first plan",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "planner",
       "action": "llm_plan",
       "detail": "intent=field_of_event",
       "tokens": 819,
       "latency": 2.319,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_vertex_lookup",
       "detail": "iteration 1: field_of_event",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    },
    "occam": {
     "answer": "26",
     "correct": true,
     "tokens": 0,
     "latency": 0.0,
     "tier": "tier0_rule_graph",
     "stop": "answered at tier 0 with no LLM call",
     "recall": 1.0,
     "docs": 1,
     "steps": [
      {
       "agent": "router",
       "action": "rule_match",
       "detail": "matched rule:field_of_event",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      },
      {
       "agent": "graph",
       "action": "graph_vertex_lookup",
       "detail": "tier 0: field_of_event",
       "tokens": 0,
       "latency": 0.0,
       "outcome": "ok"
      }
     ]
    }
   }
  }
 ]
};
