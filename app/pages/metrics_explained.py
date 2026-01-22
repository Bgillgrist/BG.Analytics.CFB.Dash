import streamlit as st
import textwrap

H1_SIZE = "2.8rem"   # main page header
H2_SIZE = "1.8rem"   # block header inside
BODY_SIZE = "1.15rem"

st.markdown(textwrap.dedent(f"""
<div style="font-size:{H1_SIZE}; font-weight:900; margin-bottom:1rem;">
  1. What are Power Ratings and why do we use them?
</div>

<div style="font-size:2.3rem; font-weight:900; margin-bottom:1rem;">
  Why do we need / use power ratings?
</div>

<!-- ========================= -->
<!-- GROUP 1 WRAPPER (Blocks 1–2) -->
<!-- ========================= -->
<div style="
  border-left: 10px solid #000000;
  padding-left: 1.25rem;
  margin-bottom: 1.75rem;
">

  <!-- Block 1 -->
  <div style="
    border-left: 4px solid #FC0000;
    padding-left: 1rem;
    margin-bottom: 1.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      The Main Idea
    </div>
    Power Ratings are a way to measure how good a team <strong>actually</strong> is,
    not just what the team’s record shows.
    <br><br>
    We know that not all teams with the same record are built the same, so we create Power
    Ratings to put all teams on even ground to accurately compare two teams regardless of
    their conference or situation.
    <br><br>
    To understand how this works, we first need to answer one question:
    <br>
    <em>What does it mean for a team to be “better” than another team?</em>
  </div>

  <!-- Block 2 -->
  <div style="
    border-left: 4px solid #FC7E00;
    padding-left: 1rem;
    margin-bottom: 0.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      How do we determine which of two teams is better?
    </div>
    There are many different ways to do this that I hear from people. The main one 
    is usually "Head to Head" results but I think its clear that no one really holds 
    head to head as the standard because we all know that upsets can happen. An FCS team beating 
    a good FBS team obviouly wouldn't mean that they are better.
    <br><br>
    Some people would look to specific stats like average MOV or maybe even a more 
    advanced metric like the BCS Rankings, but these metrics will never 
    contain every piece of information about a team necessary to determine which 
    team is better.
    <br><br>
    So what do we do? Is there a way to determine this? In short, no. No single game 
    result or metric will every be able to truly answer this question. I believe the 
    only way to determine which team is "better" would be to have the two teams play 
    a large number of games (at least 30) on a neutral field and pick the team that wins 
    &gt; 50% of those games. Obviously this will never happen so what do we do? The best way 
    is to create an "estimate".
    <br><br>
    Since the goal is to create power ratings that would correctly predict the team that wins at 
    least 16/30 hypothetical future games, we want to create our power ratings that have the best 
    predictive performance on future outcomes. The first thing that comes to mind are Vegas models 
    however the ratings used in their models are not publicaly available to use. Therefore, we must 
    create our own ratings but how do we do that?
  </div>

</div>  <!-- END GROUP 1 -->

<!-- ========================= -->
<!-- GROUP 2 WRAPPER (Block 3 only) -->
<!-- ========================= -->
<div style="font-size:2.3rem; font-weight:900; margin-bottom:1rem;">
  How do Power Ratings work?
</div>

<div style="
  border-left: 10px solid #000000;
  padding-left: 1.25rem;
  margin-bottom: 1.75rem;
">

  <!-- Block 3 -->
  <div style="
    border-left: 4px solid #FCFC00;
    padding-left: 1rem;
    margin-bottom: 0.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      How do we create our own power ratings?
    </div>
    write out here...
  </div>

</div>  <!-- END GROUP 2 -->
"""), unsafe_allow_html=True)