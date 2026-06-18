import streamlit as st 
from database import init_db, add_memory, get_memories


init_db()

st.title("JARVIS memory system")
memory = st.text_input("Store a memory")

if st.button("Save Memory"):
    if memory:
        add_memory(memory)
        st.success("Memory saved!")


st.subheader("your Memories")

memories = get_memories()

for m in memories:
    st.write("•", m)
                   

#.\.venv\Scripts\Activate.ps1