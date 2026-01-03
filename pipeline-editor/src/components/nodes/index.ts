import { StageNode } from './StageNode'
import { AgentNode } from './AgentNode'
import { QueueNode } from './QueueNode'
import { DecisionNode } from './DecisionNode'
import { CodeSnippetNode } from './CodeSnippetNode'
import { SubtaskNode } from './SubtaskNode'

export const nodeTypes = {
  stage: StageNode,
  agent: AgentNode,
  queue: QueueNode,
  decision: DecisionNode,
  code_snippet: CodeSnippetNode,
  subtask: SubtaskNode,
}

export { StageNode, AgentNode, QueueNode, DecisionNode, CodeSnippetNode, SubtaskNode }
