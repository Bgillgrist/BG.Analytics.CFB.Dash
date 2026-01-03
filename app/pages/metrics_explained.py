import streamlit as st
import textwrap

##################
# Power Ratings Section

# The Main Idea
st.markdown(
    textwrap.dedent("""
<div style="font-size:2.2rem; font-weight:800; margin-bottom:0.75rem;">
  What are Power Ratings?
</div>

<div style="
  border-left: 4px solid #FC0000;
  padding-left: 1rem;
  margin-bottom: 1.25rem;
  font-size: 1.15rem;
  font-weight: 500;
  line-height: 1.7;
  font-family: inherit;
">
  <strong>The Main Idea:</strong><br><br> 
                    
  Power Ratings are a way to measure how good a team <strong>actually</strong> is, 
  not just what the team’s record shows.

  We know that not all teams with the same record are built the same so we create Power 
  Ratings to put all teams on even ground to accurately compare
  two teams regardless of their conference or situation.

  To understand how this works, we first need to answer one question:

  <em>What does it mean for a team to be “better” than another team?</em>
</div>
"""),
    unsafe_allow_html=True
)

# What makes a team better than another?
st.markdown(
    textwrap.dedent("""
<div style="
border-left: 4px solid #FC7E00;
padding-left: 1rem;
margin-bottom: 1.25rem;
font-size: 1.15rem;
font-weight: 500;
line-height: 1.7;
font-family: inherit;
">
<strong>How do we determine which of two teams is better?</strong><br><br>

There are many different ways to do this that I hear from people. The main one 
is usually "Head to Head" results but I think its clear that no one really holds 
head to head as the standard as its clear that upsets do happen. an FCS team beating 
a good FBS team obviouly wouldn't mean that they are better.

Some people would look to specific stats like average MOV, maybe even a more advanced 
metric like the BCS Rankings or the ESPN FPI, but these metrics will never 
contain every piece of information about a team necessary to determine which 
team is better.

So what do we do? Is there a way to determine this? In short, no. No single game 
result or metric will every be able to truly answer this question. I believe the 
only way to determine which team is "better" would be to have the two teams play 
a large number of games (at least 30) on a neutral field and pick the team that wins 
&gt; 50% of those games. Obviously this will never happen so what do we do? The best way 
is to create an "estimate".

Everybody creates their own "estimate" whether they realize it or not. If you choose 
win-loss record to compare two teams, you are using # of wins as your estimate. If 
you use a specific stat, you are using that metric as your estimate. So what estimate 
is best? Given that none of these are objective truths, there is no one estimate that
is the "best" so what should we use?
</div>
"""),
    unsafe_allow_html=True
)

st.markdown(
    textwrap.dedent("""
<div style="
border-left: 4px solid #FCFC00;
padding-left: 1rem;
margin-bottom: 1.25rem;
font-size: 1.15rem;
font-weight: 500;
line-height: 1.7;
font-family: inherit;
">
<strong>What is the best estimate of team "Power"</strong><br><br>

blah blah blah

</div>
"""),
    unsafe_allow_html=True
)