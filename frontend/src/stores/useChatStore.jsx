import { create } from "zustand";

/**
 * Connection states for the chat WebSocket, surfaced in the UI as a status badge.
 * The socket itself is NOT held here: per the IntelOwl convention zustand stores keep only
 * serializable state, so the WebSocket (and its timers) live in the useChatWebSocket hook via
 * refs. This store is the single source of truth for what the panel renders; the hook owns the
 * transport and calls the apply* reducers below as frames arrive.
 */
export const ConnectionState = Object.freeze({
  IDLE: "idle",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  CLOSED: "closed",
});

export const MessageRole = Object.freeze({
  USER: "user",
  ASSISTANT: "assistant",
});

const initialTurnState = {
  // text of the assistant answer while it streams token-by-token (committed to messages on `end`)
  streamingText: "",
  // name of the tool the agent is currently running, shown as a "Running <tool>…" indicator
  currentTool: null,
  // true between sending a message and receiving `end`/`error`; disables the composer
  isStreaming: false,
};

export const useChatStore = create((set) => ({
  // drawer visibility (toggled from the global header, a separate component subtree)
  isOpen: false,
  // session id assigned by the server in the `ack` frame; null until the first turn binds it
  sessionId: null,
  // committed conversation: [{ id?, role, content }]
  messages: [],
  ...initialTurnState,
  connectionState: ConnectionState.IDLE,
  // last user-facing error text (cleared when a new turn starts)
  error: null,

  // --- drawer actions ---
  toggle: () => set((state) => ({ isOpen: !state.isOpen })),
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),

  // --- outbound ---
  // Optimistically render the user's message and lock the composer before the server replies.
  enqueueUserMessage: (text) =>
    set((state) => ({
      messages: [...state.messages, { role: MessageRole.USER, content: text }],
      ...initialTurnState,
      isStreaming: true,
      error: null,
    })),

  // --- inbound frame reducers (called by the hook; demux/filtering happens upstream there) ---
  applyAck: (event) => set({ sessionId: event.session_id }),
  applyStart: () =>
    set({ ...initialTurnState, isStreaming: true, error: null }),
  applyStatus: (event) => set({ currentTool: event.tool }),
  applyToken: (event) =>
    set((state) => ({ streamingText: state.streamingText + event.content })),
  applyEnd: (event) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: event.message_id,
          role: MessageRole.ASSISTANT,
          content: event.content,
        },
      ],
      ...initialTurnState,
    })),
  // `detail` is the server's user-safe text, or a client-side message for the watchdog timeouts.
  // The partial streaming bubble is dropped (the server drops the turn too) but the user's message
  // stays visible so they can retry.
  applyError: (detail) => set({ ...initialTurnState, error: detail }),

  // --- connection ---
  setConnectionState: (connectionState) => set({ connectionState }),
}));
