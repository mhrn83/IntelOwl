import {
  useChatStore,
  ConnectionState,
  MessageRole,
} from "../../src/stores/useChatStore";

const initialState = {
  isOpen: false,
  sessionId: null,
  messages: [],
  streamingText: "",
  currentTool: null,
  isStreaming: false,
  connectionState: ConnectionState.IDLE,
  error: null,
};

describe("useChatStore reducers", () => {
  beforeEach(() => {
    useChatStore.setState(initialState);
  });

  test("toggle flips isOpen", () => {
    useChatStore.getState().toggle();
    expect(useChatStore.getState().isOpen).toBe(true);
    useChatStore.getState().toggle();
    expect(useChatStore.getState().isOpen).toBe(false);
  });

  test("applyAck binds the session id", () => {
    useChatStore.getState().applyAck({ session_id: 42 });
    expect(useChatStore.getState().sessionId).toBe(42);
  });

  test("enqueueUserMessage appends the user message and locks the turn", () => {
    useChatStore.setState({ error: "stale" });
    useChatStore.getState().enqueueUserMessage("hello");
    const state = useChatStore.getState();
    expect(state.messages).toEqual([
      { role: MessageRole.USER, content: "hello" },
    ]);
    expect(state.isStreaming).toBe(true);
    expect(state.error).toBeNull();
  });

  test("applyStart resets the streaming turn", () => {
    useChatStore.setState({
      streamingText: "leftover",
      currentTool: "search_jobs",
    });
    useChatStore.getState().applyStart();
    const state = useChatStore.getState();
    expect(state.streamingText).toBe("");
    expect(state.currentTool).toBeNull();
    expect(state.isStreaming).toBe(true);
  });

  test("applyStatus sets the current tool", () => {
    useChatStore.getState().applyStatus({ tool: "get_job_details" });
    expect(useChatStore.getState().currentTool).toBe("get_job_details");
  });

  test("applyToken appends streaming text incrementally", () => {
    useChatStore.getState().applyToken({ content: "Hel" });
    useChatStore.getState().applyToken({ content: "lo" });
    expect(useChatStore.getState().streamingText).toBe("Hello");
  });

  test("applyEnd commits the assistant message and clears the turn", () => {
    useChatStore.setState({
      streamingText: "Hel",
      currentTool: "search_jobs",
      isStreaming: true,
    });
    useChatStore.getState().applyEnd({ message_id: 7, content: "Hello there" });
    const state = useChatStore.getState();
    expect(state.messages).toEqual([
      { id: 7, role: MessageRole.ASSISTANT, content: "Hello there" },
    ]);
    expect(state.streamingText).toBe("");
    expect(state.currentTool).toBeNull();
    expect(state.isStreaming).toBe(false);
  });

  test("applyError surfaces the detail and ends the turn", () => {
    useChatStore.setState({ streamingText: "partial", isStreaming: true });
    useChatStore.getState().applyError("boom");
    const state = useChatStore.getState();
    expect(state.error).toBe("boom");
    expect(state.isStreaming).toBe(false);
    expect(state.streamingText).toBe("");
  });

  test("setConnectionState updates the badge state", () => {
    useChatStore.getState().setConnectionState(ConnectionState.CONNECTED);
    expect(useChatStore.getState().connectionState).toBe(
      ConnectionState.CONNECTED,
    );
  });
});
