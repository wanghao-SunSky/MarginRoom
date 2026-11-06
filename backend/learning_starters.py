"""Human-reviewed starters for the pinned, bundled Rust Book excerpt (2026-11-06)."""
RUST_STARTERS={
 'Functions':('main 和 fn 各有什么作用？请结合本节代码解释。','What do main and fn do? Explain using this section’s code.'),
 'Parameters':('参数和传入的具体值有什么区别？为什么参数要声明类型？','How do parameters differ from arguments, and why do parameters declare types?'),
 'Statements and Expressions':('给表达式末尾加分号，为什么会改变函数返回值？','Why can adding a semicolon to an expression change a function’s return value?'),
 'Functions with Return Values':('five 函数没有 return 语句，为什么仍能返回 5？','Why can the five function return 5 without a return statement?'),
 'What Is Ownership?':('所有权怎样让 Rust 在没有垃圾回收器的情况下管理内存？','How does ownership let Rust manage memory without a garbage collector?'),
 'Ownership Rules':('当所有者离开作用域时会发生什么？请按本节三条规则解释。','What happens when an owner goes out of scope? Explain using the three rules.'),
 'Variable Scope':('变量进入和离开作用域，分别意味着什么？','What does it mean for a variable to enter and leave scope?'),
 'The `String` Type':('String 与字符串字面量有什么区别，为什么这里需要 String？','How does String differ from a string literal, and why is String useful here?'),
 'Memory and Allocation':('把一个 String 赋给另一个变量后，为什么原变量不能继续使用？','Why can’t the original variable be used after assigning its String to another variable?'),
 'Ownership and Functions':('把 String 传给函数与把整数传给函数，所有权变化有什么不同？','How does passing a String to a function differ from passing an integer?'),
 'Return Values and Scope':('函数返回一个 String 时，所有权如何回到调用处？','How does ownership pass to the caller when a function returns a String?'),
 'References and Borrowing':('calculate_length 使用 &String，为什么不必把 String 再返回？','Why does calculate_length with &String not need to return the String?'),
 'Mutable References':('为什么同一作用域里的可变引用不能与正在使用的其他引用并存？','Why can’t an active mutable reference coexist with other active references to the same data?'),
 'Dangling References':('dangle 为什么不能返回指向局部 String 的引用？','Why can’t dangle return a reference to its local String?'),
 'The Rules of References':('本节对引用数量和有效性分别有什么要求？','What are this section’s rules about reference counts and validity?'),
 'The Slice Type':('只返回单词结束位置的数字有什么隐患，切片怎样解决？','What can go wrong when returning only a word’s end index, and how do slices help?'),
 'String Slices':('字符串切片如何与原始 String 保持关联？','How does a string slice remain tied to the original String?'),
 'Other Slices':('数组切片与字符串切片有什么共同点？','What do array slices and string slices have in common?'),
 'Summary':('所有权、借用和切片分别怎样保证内存安全？','How do ownership, borrowing, and slices each contribute to memory safety?'),
}

# Only offer reviewed questions for a known source and a matching section.
CS329Z_STARTERS={
 '第 01 讲｜Agent 基础与全景':('聊天模型和 Agent 到底差在哪？用一个实际任务说明。','What makes an Agent different from a chat model? Show me with a real task.'),
 '1. 课程定位与学习方式':('为什么学 Agent 不能只学怎么调用模型 API？','Why is learning to call a model API not enough to build an Agent?'),
 '2. Agent 概念的历史':('这里说的“自主性”，和按预设流程执行有什么区别？','How does autonomy differ from following a predefined workflow?'),
 '3. Agent 的组成与推理':('一次工具调用结束后，Agent 怎么决定下一步做什么？','After a tool call finishes, how does an Agent decide what to do next?'),
 '4. 记忆的三种作用':('对话历史和长期记忆有什么区别？用一个任务解释。','How does conversation history differ from long-term memory? Use a task as an example.'),
 '5. 工具与复合系统':('什么任务适合固定工作流，什么任务才需要 Agent？','When is a fixed workflow enough, and when do you need an Agent?'),
 '6. 关键挑战与研究问题':('为什么每一步都很准，整个任务仍可能失败？','Why can a whole task fail even when each individual step is usually correct?'),
}
